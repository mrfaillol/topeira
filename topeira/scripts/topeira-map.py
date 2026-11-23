#!/usr/bin/env python3
"""topeira-map — mapa read-only do disco + página visual (treemap + recomendações).

Nunca apaga, move ou abre conteúdo de arquivo. Só faz lstat/scandir, que não baixam
placeholders do iCloud. Gera <out>/mapa.json e <out>/mapa.html.

A página não gera script de limpeza: ela monta um PEDIDO DE APROVAÇÃO em texto, que o
usuário cola de volta na conversa. A execução continua sendo da Topeira, categoria por
categoria, com medição antes/depois (red line never_batch_without_category_confirmation).

Uso:
  python3 topeira-map.py                       # volume de dados inteiro
  python3 topeira-map.py --roots ~             # só a home (mais rápido)
  python3 topeira-map.py --redact              # recolhe nomes dentro de Documents/iCloud/Desktop
  python3 topeira-map.py --no-open --out DIR
  python3 topeira-map.py --render ~/.local/state/topeira/mapas/<id>/mapa.json
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
import os
import re
import socket
import stat
import struct
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

HOME = str(Path.home())
DATA_PREFIX = "/System/Volumes/Data"
SF_DATALESS = 0x40000000  # placeholder do iCloud: alocação local zero
STATE_DIR = Path(HOME) / ".local/state/topeira/mapas"
KEEP_MAPS = 5
WHITELIST = Path(HOME) / ".config/mole/whitelist"
TEMPLATE = Path(__file__).with_name("topeira-map.template.html")

# ---------------------------------------------------------------------------
# Regras de classificação. Caminhos em forma de exibição (~ = home).
# rec = id de recomendação (aparece no painel); sem rec = só classifica.
# tier: A seguro · B revisar antes · C seu acervo · D protegido · "" sem proposta
# ---------------------------------------------------------------------------
RECS = {
    "npm":        ("Cache do npm", "A", "npm cache clean --force", "Recriado sob demanda pelo npm."),
    "brew":       ("Cache do Homebrew", "A", "brew cleanup -s --prune=all", "Downloads antigos de fórmulas."),
    "pip":        ("Cache do pip", "A", "pip cache purge", "Wheels baixadas; venvs não dependem dele."),
    "yarn":       ("Cache do Yarn", "A", "yarn cache clean", "Pacotes baixados."),
    "gobuild":    ("Cache de build do Go", "A", "go clean -cache", "Recompilado sob demanda."),
    "puppeteer":  ("Navegadores do Puppeteer", "A", "apagar a pasta listada", "Baixado de novo no próximo uso."),
    "gradle":     ("Caches do Gradle", "A", "apagar ~/.gradle/caches", "Baixado de novo no próximo build."),
    "xcode-dd":   ("Xcode DerivedData", "A", "apagar o conteúdo de DerivedData", "Build intermediário; Xcode refaz."),
    "sim-cache":  ("Caches do Simulator", "A", "apagar o conteúdo da pasta", "Recriado pelo Simulator."),
    "app-caches": ("Caches de apps", "A", "apagar o conteúdo de cada pasta listada, com o app fechado", "Cache recriável; whitelist e apps abertos ficam de fora."),
    "logs":       ("Logs de apps", "A", "apagar logs antigos das pastas listadas", "Diagnóstico antigo; Claude/ fica de fora (whitelist)."),
    "build-out":  ("Saída de build (.next, .turbo)", "A", "apagar as pastas listadas", "Gerado de novo no próximo build; parar dev server antes."),
    "electron":   ("Caches Electron dentro de Application Support", "A", "apagar só estas subpastas de cache, com o app fechado", "Cache/Code Cache/GPUCache/CachedData de cada app; dados do app ficam intocados."),
    "claude-vm":  ("VM do Claude Desktop", "B", "apagar com o Claude fechado; o app baixa de novo (~13 GB)", "Red line: nunca com a VM rodando."),
    "docker-stg": ("Atualização do Docker interrompida", "B", "concluir o update pelo app ou apagar o staging", "Staging de uma versão baixada e não instalada."),
    "uv":         ("Cache do uv", "B", "uv cache clean", "Em 11/10 ficou retido porque estava em uso — checar processos."),
    "playwright": ("Navegadores do Playwright", "B", "apagar e reinstalar com npx playwright install", "Testes E2E dependem deles."),
    "gradle-wr":  ("Distribuições do Gradle wrapper", "B", "apagar versões antigas", "Projetos antigos podem pedir de novo."),
    "xcode-ds":   ("Xcode DeviceSupport", "B", "apagar versões de iOS/watchOS que você não usa mais", "Rebaixado quando um aparelho conecta."),
    "simulators": ("Simuladores do Xcode", "B", "xcrun simctl delete unavailable", "Simuladores de runtimes que não existem mais."),
    "android-sdk":("Android SDK", "B", "remover plataformas/imagens sem uso pelo sdkmanager", "Pesado e custoso de rebaixar."),
    "android-avd":("Emuladores Android", "B", "apagar AVDs sem uso", "Discos de emulador com estado."),
    "node-mod":   ("node_modules em projetos", "B", "apagar só de projetos parados (npm install recria)", "Confirmar que o projeto não está ativo."),
    "venv":       ("Ambientes Python (.venv) em projetos", "B", "apagar só de projetos parados", "Recriável se houver requirements/lockfile."),
    "pods":       ("CocoaPods em projetos", "B", "apagar Pods/ de projetos parados (pod install recria)", "Confirmar projeto parado."),
    "worktrees":  ("Worktrees de agentes", "B", "git worktree remove sem --force, depois de checar commits/untracked", "Pode ter trabalho não mergeado; regra do drill contínuo."),
    "codex-viz":  ("Artefatos de auditoria do Codex", "B", "conferir recibos/ZIPs antes; staging da própria Topeira entra aqui", "Inclui cópias de preparação de rodadas anteriores."),
    "xcode-arc":  ("Xcode Archives", "C", "apagar builds que você não vai reenviar", "Builds assinados; só você sabe se ainda servem."),
    "trash":      ("Lixeira", "C", "esvaziar pelo Finder", "Já foi para o lixo; conferir antes."),
    "downloads":  ("Downloads", "C", "revisar arquivos antigos", "Pode ter instaladores e arquivos pessoais misturados."),
    "movies":     ("Filmes e gravações", "C", "revisar gravações antigas", "Acervo pessoal."),
}

EXACT = {
    "~/.npm/_cacache": ("cache", "A", "npm"), "~/.npm/_npx": ("cache", "A", "npm"),
    "~/.npm/_logs": ("cache", "A", "npm"), "~/.npm/_prebuilds": ("cache", "A", "npm"),
    "~/Library/Caches/Homebrew": ("cache", "A", "brew"),
    "~/Library/Caches/pip": ("cache", "A", "pip"), "~/.cache/pip": ("cache", "A", "pip"),
    "~/Library/Caches/Yarn": ("cache", "A", "yarn"),
    "~/Library/Caches/go-build": ("cache", "A", "gobuild"),
    "~/.cache/puppeteer": ("cache", "A", "puppeteer"),
    "~/.cache/uv": ("cache", "B", "uv"),
    "~/.cache/ms-playwright": ("cache", "B", "playwright"),
    "~/Library/Caches/ms-playwright": ("cache", "B", "playwright"),
    "~/.gradle/caches": ("cache", "A", "gradle"),
    "~/.gradle/wrapper/dists": ("cache", "B", "gradle-wr"),
    "~/Library/Developer/Xcode/DerivedData": ("dev", "A", "xcode-dd"),
    "~/Library/Developer/Xcode/Archives": ("dev", "C", "xcode-arc"),
    "~/Library/Developer/Xcode/iOS DeviceSupport": ("dev", "B", "xcode-ds"),
    "~/Library/Developer/Xcode/watchOS DeviceSupport": ("dev", "B", "xcode-ds"),
    "~/Library/Developer/CoreSimulator/Devices": ("dev", "B", "simulators"),
    "~/Library/Developer/CoreSimulator/Caches": ("dev", "A", "sim-cache"),
    "~/Library/Android/sdk": ("dev", "B", "android-sdk"),
    "~/.android/avd": ("dev", "B", "android-avd"),
    "~/.Trash": ("docs", "C", "trash"),
    "~/Downloads": ("docs", "C", "downloads"),
    "~/Movies": ("docs", "C", "movies"),
    "~/.codex/visualizations": ("ai", "B", "codex-viz"),
    # Sem proposta: histórico de agentes só sai por lotes do drill contínuo.
    "~/.codex": ("ai", "D", None), "~/.claude": ("ai", "D", None),
    "~/.cursor": ("ai", "D", None), "~/.local/share/opencode": ("ai", "D", None),
    "~/Library/Application Support/Cursor": ("ai", "D", None),
    "~/Library/Application Support/Claude": ("ai", "D", None),
    "~/.ollama": ("ai", "D", None),
    "~/.cache": ("cache", "", None), "~/.npm": ("cache", "", None),
    "~/Library/Caches": ("cache", "", None), "~/Library/Logs": ("apps", "", None),
    "~/Library/Developer": ("dev", "", None), "~/Library/Android": ("dev", "", None),
    "~/.android": ("dev", "", None), "~/.gradle": ("cache", "", None),
    "~/Documents": ("docs", "D", None), "~/Desktop": ("docs", "D", None),
    "~/Library/Mobile Documents": ("docs", "D", None),
    "~/Pictures": ("docs", "D", None), "~/Music": ("docs", "D", None),
    "~/Library/Mail": ("personal", "D", None), "~/Library/Messages": ("personal", "D", None),
    "~/.ssh": ("personal", "D", None), "~/.gnupg": ("personal", "D", None),
    "~/Library/Keychains": ("personal", "D", None),
    "~/Library/Application Support": ("apps", "D", None),
    "~/Library/Group Containers": ("apps", "D", None),
    "~/Library/Application Support/Steam": ("games", "D", None),
    "~/Library/Application Support/Claude/vm_bundles": ("ai", "B", "claude-vm"),
    "~/Library/Application Support/com.docker.install/in_progress": ("dev", "B", "docker-stg"),
    "~/Library/Application Support/Cursor/snapshots": ("ai", "D", None),
    "~/Library/Application Support/Cursor/User": ("ai", "D", None),
    "~/Library/Application Support/CrossOver": ("games", "D", None),
    "~/Projects": ("code", "", None), "~/Projects_Local": ("code", "", None),
    "~/Library": ("apps", "", None),
    "/Applications": ("apps", "", None), "/opt/homebrew": ("dev", "", None),
    "/Library": ("system", "", None), "/private": ("system", "", None),
    "/private/var/vm": ("system", "D", None), "/usr": ("system", "", None),
    "/System": ("system", "", None), "/Users/Shared": ("other", "", None),
}

APP_SUPPORT = "~/Library/Application Support"
ELECTRON_CACHE = {"Cache", "Code Cache", "GPUCache", "CachedData", "DawnCache", "DawnGraphiteCache",
                  "DawnWebGPUCache", "ShaderCache", "GrShaderCache", "Crashpad", "logs"}
# Dados de app por dono: só muda a cor; continua tier D.
APP_OWNER = {"ai": {"Claude", "Cursor", "Codex", "ai.opencode.desktop", "t3code", "Hermes", "Antigravity",
                    "ZCode", "Grok Bot", "openmausbot", "Cue", "Granola"},
             "games": {"CrossOver", "Steam"}, "dev": {"Zed", "com.docker.install", "Docker Desktop"}}

CHILD_OF = {
    "~/Library/Caches": ("cache", "A", "app-caches"),
    "~/Library/Logs": ("apps", "A", "logs"),
}

# Nomes de pasta que só valem dentro de áreas de código.
NAME = {
    "node_modules": ("cache", "B", "node-mod"), ".next": ("cache", "A", "build-out"),
    ".turbo": ("cache", "A", "build-out"), ".venv": ("cache", "B", "venv"),
    "venv": ("cache", "B", "venv"), "Pods": ("cache", "B", "pods"),
    "DerivedData": ("dev", "A", "xcode-dd"),
}
def is_farm(name: str) -> bool:
    """Pastas que só guardam worktrees (ex.: repo-wt, repo-worktrees, .claude/worktrees)."""
    return name == "worktrees" or name.endswith("-wt") or name.endswith("-worktrees")


CODE_HINTS = ("/Projects/", "/Projects_Local/", "/Desktop/", "/Developer/", "/worktrees/",
              "/repos/", "~/code/", "~/src/")
# Nunca dentro destes: dependências de ferramenta instalada, não de projeto (apagar quebra plugin/CLI).
CODE_EXCLUDE = ("/plugins/", "/extensions/", "/.nvm/", "/.bun/", "/node_modules/", "/.local/share/",
                "/.npm/", "/.cache/")

# Não descer: varrer aqui trava ou mente (TCC), ou é red line.
NO_DESCEND = {
    "~/Library/Containers": "red line: não varrer Containers (TCC trava du e rm)",
}
# Fan-out com threads só nestes níveis (lstat libera o GIL; ~32 threads no máximo).
PARALLEL_AT = {"/", "/Users", "~", "~/Library", "~/Projects", "~/Library/Application Support"}
TCC_PROBE = ("~/Library/Messages", "~/Library/Mail", "~/Library/Safari",
             "~/Library/Group Containers", "~/Pictures/Photos Library.photoslibrary")
REDACT_UNDER = ("~/Documents", "~/Library/Mobile Documents", "~/Desktop", "~/Pictures",
                "~/Library/Mail", "~/Library/Messages")


class _AttrList(ctypes.Structure):
    _fields_ = [("bitmapcount", ctypes.c_ushort), ("reserved", ctypes.c_uint16),
                ("commonattr", ctypes.c_uint32), ("volattr", ctypes.c_uint32),
                ("dirattr", ctypes.c_uint32), ("fileattr", ctypes.c_uint32),
                ("forkattr", ctypes.c_uint32)]


_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
_AL = _AttrList(5, 0, 0, 0, 0, 0, 0x8)  # ATTR_CMNEXT_PRIVATESIZE
_BUF = ctypes.create_string_buffer(64)


def private_size(path: str) -> int:
    """Bytes que só este arquivo ocupa (clones APFS compartilhados contam 0).
    Soma de private = ganho MÍNIMO garantido; soma de alocado = teto."""
    if _libc.getattrlist(path.encode(), ctypes.byref(_AL), _BUF, 64, 0x20 | 0x1) != 0:
        return 0
    return struct.unpack_from("=Iq", _BUF.raw)[1]


def important_free() -> int | None:
    """O número que o Finder mostra (inclui purgeable). Reportar só o livre do APFS
    engana: os dois números precisam aparecer."""
    code = ('import Foundation; let v = try! URL(fileURLWithPath: "/").resourceValues('
            'forKeys: [.volumeAvailableCapacityForImportantUsageKey]); '
            'print(v.volumeAvailableCapacityForImportantUsage ?? -1)')
    try:
        out = subprocess.run(["swift", "-e", code], capture_output=True, text=True, timeout=60)
        n = int(out.stdout.strip())
        return n if n >= 0 else None
    except Exception:
        return None


def disp(real: str) -> str:
    if real == DATA_PREFIX:
        return "/"
    if real.startswith(DATA_PREFIX + "/"):
        real = real[len(DATA_PREFIX):]
    if real == HOME:
        return "~"
    if real.startswith(HOME + "/"):
        return "~" + real[len(HOME):]
    return real


def load_whitelist() -> re.Pattern | None:
    """Whitelist do Mole tem grafias históricas da home (beijaflor). Resolve contra a home real;
    grafia errada não é permissão para limpar a categoria."""
    if not WHITELIST.exists():
        return None
    pats = []
    for line in WHITELIST.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^/Users/[^/]+", HOME, line)
        # Montado à mão: fnmatch.translate muda de terminador entre versões (\Z → \z no 3.14+).
        pats.append(re.escape(line).replace(r"\*", ".*") + r"(?:/|$)")
    return re.compile("|".join(pats)) if pats else None


def probe(path: str, seconds: int = 5) -> bool:
    try:
        subprocess.run(["ls", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=seconds, check=True)
        return True
    except Exception:
        return False


class Scanner:
    def __init__(self, min_bytes: int, max_depth: int, max_children: int, deadline: float,
                 redact: bool):
        self.min_bytes, self.max_depth, self.max_children = min_bytes, max_depth, max_children
        self.deadline, self.redact = deadline, redact
        self.wl = load_whitelist()
        self.seen_inodes: set[tuple[int, int]] = set()
        self.lock = threading.Lock()
        self.recs: dict[str, list[tuple[str, int]]] = {}
        self.dirs = 0
        self.denied = 0
        self.denied_paths: list[str] = []
        self.timed_out = False
        self.last_print = 0.0
        self.blocked_tcc: dict[str, str] = {}
        for p in TCC_PROBE:
            real = HOME + p[1:]
            if os.path.exists(real) and not probe(real):
                self.blocked_tcc[p] = "sem acesso (TCC/Full Disk Access)"

    def classify(self, d: str, name: str, parent_disp: str):
        if d in EXACT:
            return EXACT[d]
        if parent_disp == APP_SUPPORT:
            for cat, names in APP_OWNER.items():
                if name in names:
                    return (cat, "D", None)
        if name in ELECTRON_CACHE and parent_disp.startswith(APP_SUPPORT + "/") \
                and parent_disp.count("/") == APP_SUPPORT.count("/") + 1:
            return ("cache", "A", "electron")  # whitelist (Claude, Brave, Comet…) vence depois
        if parent_disp in CHILD_OF:
            return CHILD_OF[parent_disp]
        if name in NAME and d.startswith("~/") and not d.startswith("~/Library/") \
                and ".app/" not in d and any(h in d for h in CODE_HINTS) \
                and not any(x in d for x in CODE_EXCLUDE):
            return NAME[name]
        if name == "worktrees" and parent_disp.rsplit("/", 1)[-1] in (".claude", ".codex", ".cursor"):
            return ("code", "B", None)
        if is_farm(name) and d.startswith("~/"):
            return ("code", "B", None)
        if is_farm(parent_disp.rsplit("/", 1)[-1]) and parent_disp.startswith("~/"):
            return ("code", "B", "worktrees")  # cada worktree vira um item da lista
        return None

    def progress(self, d: str):
        now = time.time()
        if now - self.last_print > 5:
            self.last_print = now
            print(f"\r  {self.dirs:,} pastas · {d[:70]:<70}", end="", file=sys.stderr, flush=True)

    def scan(self, real: str, dev: int, depth: int, in_rec: bool) -> dict:
        d = disp(real)
        name = os.path.basename(real) or real
        node = {"n": name, "a": 0, "l": 0, "f": 0}
        if in_rec:
            node["e"] = 0
        if d in NO_DESCEND:
            node["x"] = NO_DESCEND[d]
            return node
        if d in self.blocked_tcc:
            node["x"] = self.blocked_tcc[d]
            return node
        if time.time() > self.deadline:
            self.timed_out = True
            node["x"] = "tempo esgotado: não medido"
            return node
        self.dirs += 1
        self.progress(d)
        kids: list[dict] = []
        cloud = 0
        try:
            it = os.scandir(real)
        except OSError:
            self.denied += 1
            if len(self.denied_paths) < 200:
                self.denied_paths.append(d)
            node["x"] = "sem permissão"
            return node
        dirs: list[tuple[str, str]] = []
        with it:
            for e in it:
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                if st.st_dev != dev:
                    continue  # outro volume
                if stat.S_ISDIR(st.st_mode):
                    dirs.append((e.path, e.name))
                elif stat.S_ISREG(st.st_mode):
                    if st.st_nlink > 1:
                        key = (st.st_dev, st.st_ino)
                        with self.lock:
                            if key in self.seen_inodes:
                                continue
                            self.seen_inodes.add(key)
                    alloc = st.st_blocks * 512
                    node["a"] += alloc; node["l"] += st.st_size; node["f"] += 1
                    if in_rec and alloc:
                        node["e"] += min(private_size(e.path), alloc)  # compressão APFS infla o private
                    if getattr(st, "st_flags", 0) & SF_DATALESS:
                        cloud += st.st_size
                    if alloc >= self.min_bytes:
                        kids.append({"n": e.name, "a": alloc, "l": st.st_size, "f": 1, "z": 1})

        def one(path_name):
            path, nm = path_name
            child_disp = d.rstrip("/") + "/" + nm if d != "/" else "/" + nm
            rule = self.classify(child_disp, nm, d)
            listed = bool(self.wl and self.wl.match(HOME + child_disp[1:] if child_disp.startswith("~") else child_disp))
            if listed:  # whitelist vence qualquer regra: vira protegido e nunca entra no pedido
                rule = ((rule[0] if rule else "apps"), "D", None)
            child_rec = rule[2] if rule and rule[2] and not in_rec else None
            child = self.scan(path, dev, depth + 1, in_rec or bool(child_rec))
            if rule:
                child["c"], child["t"] = rule[0], rule[1]
                if child_rec:
                    child["r"] = child_rec
                    if child["a"] > 0:
                        with self.lock:
                            self.recs.setdefault(child_rec, []).append(
                                (child_disp, child["a"], child.get("e", 0)))
            if listed:
                child["w"] = 1
            return child

        if (d in PARALLEL_AT or is_farm(name)) and len(dirs) > 1:
            with ThreadPoolExecutor(max_workers=8) as pool:
                children = list(pool.map(one, dirs))
        else:
            children = [one(x) for x in dirs]
        for child in children:
            node["a"] += child["a"]; node["l"] += child["l"]; node["f"] += child["f"]
            if in_rec:
                node["e"] += child.get("e", 0)
            cloud += child.get("cl", 0)
            kids.append(child)
        if cloud:
            node["cl"] = cloud
        if self.redact and any(d == r or d.startswith(r + "/") for r in REDACT_UNDER) \
                and d not in REDACT_UNDER:
            return node  # esconde nomes abaixo do primeiro nível dessas áreas
        if depth < self.max_depth:
            keep = sorted((k for k in kids if k["a"] >= self.min_bytes or "x" in k),
                          key=lambda k: -k["a"])
            cap = 400 if is_farm(name) else self.max_children  # cada worktree visível
            rest = keep[cap:]
            keep = keep[:cap]
            small = [k for k in kids if k not in keep]
            if small:
                other = {"n": f"(outros · {len(small):,})", "a": sum(k["a"] for k in small),
                         "l": sum(k["l"] for k in small), "f": sum(k["f"] for k in small), "o": 1}
                if other["a"] >= self.min_bytes:
                    keep.append(other)
            del rest
            if keep:
                node["k"] = keep
        return node


def volume_info(root: str) -> dict:
    """Usado POR VOLUME vem do df (statvfs dá o container APFS inteiro)."""
    v = os.statvfs(root)
    info = {"total": v.f_blocks * v.f_frsize, "avail": v.f_bavail * v.f_frsize,
            "used": (v.f_blocks - v.f_bavail) * v.f_frsize}
    try:
        line = subprocess.run(["df", "-k", root], capture_output=True, text=True,
                              timeout=10).stdout.splitlines()[1].split()
        info["used"] = int(line[2]) * 1024
    except Exception:
        pass
    return info


def snapshots() -> list[str]:
    try:
        out = subprocess.run(["tmutil", "listlocalsnapshots", "/"], capture_output=True,
                             text=True, timeout=10).stdout
        return [l.strip() for l in out.splitlines() if "com.apple" in l]
    except Exception:
        return []


def build_recs(scanner: Scanner) -> list[dict]:
    out = []
    order = {"A": 0, "B": 1, "C": 2}
    for rid, items in scanner.recs.items():
        title, tier, cmd, why = RECS[rid]
        # Segunda trava: nada da whitelist ou de tier D chega ao pedido, mesmo com bug de regra.
        safe = []
        for item in items:
            real = HOME + item[0][1:] if item[0].startswith("~") else item[0]
            if scanner.wl and scanner.wl.match(real):
                print(f"AVISO: {item[0]} está na whitelist e foi retirado das recomendações", file=sys.stderr)
                continue
            safe.append(item)
        items = safe
        items.sort(key=lambda x: -x[1])
        total = sum(a for _, a, _ in items)
        excl = sum(e for _, _, e in items)
        if total < 100 * 1024**2:
            continue
        out.append({"id": rid, "title": title, "tier": tier, "cmd": cmd, "why": why,
                    "total": total, "excl": excl, "count": len(items),
                    "paths": [{"p": p, "a": a, "e": e} for p, a, e in items[:40]]})
    out.sort(key=lambda r: (order.get(r["tier"], 9), -r["total"]))
    return out


def retire_old_maps():
    if not STATE_DIR.exists():
        return
    runs = sorted((p for p in STATE_DIR.iterdir() if p.is_dir()), key=lambda p: p.name)
    for old in runs[:-KEEP_MAPS]:
        for f in old.iterdir():
            f.unlink()
        old.rmdir()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roots", nargs="*", default=None, help="padrão: volume de dados inteiro")
    ap.add_argument("--out", default=None)
    ap.add_argument("--min-mb", type=int, default=32, help="menor nó guardado no mapa")
    ap.add_argument("--depth", type=int, default=10)
    ap.add_argument("--max-children", type=int, default=40)
    ap.add_argument("--max-seconds", type=int, default=1500)
    ap.add_argument("--redact", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--render", metavar="MAPA_JSON", help="refaz só a página a partir de um mapa.json")
    args = ap.parse_args()

    if args.render:
        src = Path(args.render)
        payload = src.read_text()
        html = TEMPLATE.read_text().replace("__TOPEIRA_DATA__", payload.replace("</", "<\\/"))
        (src.parent / "mapa.html").write_text(html)
        print(f"mapa: {src.parent / 'mapa.html'}")
        if not args.no_open:
            subprocess.run(["open", str(src.parent / "mapa.html")], check=False)
        return

    roots = [os.path.expanduser(r) for r in (args.roots or [DATA_PREFIX if os.path.isdir(DATA_PREFIX) else "/"])]
    started = time.time()
    sc = Scanner(args.min_mb * 1024**2, args.depth, args.max_children,
                 started + args.max_seconds, args.redact)
    tops = []
    for r in roots:
        r = os.path.realpath(r)
        print(f"topeira-map: varrendo {disp(r)} (só leitura)", file=sys.stderr)
        node = sc.scan(r, os.lstat(r).st_dev, 0, False)
        node["n"] = disp(r) if disp(r) != "/" else "Disco"
        node["p"] = disp(r)
        tops.append(node)
    print(file=sys.stderr)
    tree = tops[0] if len(tops) == 1 else {"n": "Raízes", "p": "", "a": sum(t["a"] for t in tops),
                                             "l": sum(t["l"] for t in tops), "f": sum(t["f"] for t in tops), "k": tops}
    vol = volume_info(roots[0])
    vol["important"] = important_free()
    ts = datetime.now().astimezone()
    meta = {
        "id": ts.strftime("%Y%m%d-%H%M%S"), "ts": ts.isoformat(timespec="seconds"),
        "host": socket.gethostname(), "roots": [disp(os.path.realpath(r)) for r in roots],
        "home": "~", "home_real": HOME, "volume": vol, "scanned": tree["a"], "snapshots": snapshots(),
        "seconds": round(time.time() - started, 1), "dirs": sc.dirs, "denied": sc.denied,
        "denied_sample": sc.denied_paths[:30], "timed_out": sc.timed_out, "redact": args.redact,
        "blocked": {**{k: v for k, v in NO_DESCEND.items()}, **sc.blocked_tcc},
        "whitelist": str(WHITELIST) if WHITELIST.exists() else None, "min_mb": args.min_mb,
    }
    data = {"meta": meta, "tree": tree, "recs": build_recs(sc)}

    out = Path(args.out) if args.out else STATE_DIR / meta["id"]
    out.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    (out / "mapa.json").write_text(payload)
    html = TEMPLATE.read_text().replace("__TOPEIRA_DATA__", payload.replace("</", "<\\/"))
    (out / "mapa.html").write_text(html)
    if not args.out:
        retire_old_maps()

    gb = lambda b: f"{b / 1e9:.1f} GB"
    print(f"mapa: {out / 'mapa.html'}")
    imp = f" ({gb(vol['important'])} p/ uso importante)" if vol.get("important") else ""
    print(f"varrido {gb(meta['scanned'])} de {gb(vol['used'])} usados · livre {gb(vol['avail'])}{imp} · "
          f"{sc.dirs:,} pastas em {meta['seconds']}s · sem permissão: {sc.denied}"
          + (" · TEMPO ESGOTADO (parcial)" if sc.timed_out else ""))
    for r in data["recs"]:
        print(f"  [{r['tier']}] {r['title']}: {gb(r['excl'])}–{gb(r['total'])} ({r['count']} pasta(s))")
    if not args.no_open:
        subprocess.run(["open", str(out / "mapa.html")], check=False)


if __name__ == "__main__":
    main()
