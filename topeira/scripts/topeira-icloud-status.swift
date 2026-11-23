import Foundation
let paths = CommandLine.arguments.dropFirst()
let keys: Set<URLResourceKey> = [.isUbiquitousItemKey,.ubiquitousItemIsUploadedKey,.ubiquitousItemIsUploadingKey,.ubiquitousItemIsDownloadingKey,.ubiquitousItemDownloadingStatusKey,.ubiquitousItemDownloadRequestedKey,.ubiquitousItemHasUnresolvedConflictsKey,.ubiquitousItemUploadingErrorKey,.ubiquitousItemDownloadingErrorKey,.ubiquitousItemIsExcludedFromSyncKey]
for path in paths {
 var o:[String:Any] = ["path":path]
 do {
  let v = try URL(fileURLWithPath:path).resourceValues(forKeys:keys)
  if let x=v.isUbiquitousItem{o["ubiquitous"]=x}; if let x=v.ubiquitousItemIsUploaded{o["uploaded"]=x}; if let x=v.ubiquitousItemIsUploading{o["uploading"]=x};if let x=v.ubiquitousItemIsDownloading{o["downloading"]=x};if let x=v.ubiquitousItemDownloadingStatus{o["download_status"]=x.rawValue};if let x=v.ubiquitousItemDownloadRequested{o["download_requested"]=x};if let x=v.ubiquitousItemHasUnresolvedConflicts{o["conflicts"]=x};if let x=v.ubiquitousItemIsExcludedFromSync{o["excluded_from_sync"]=x};if let e=v.ubiquitousItemUploadingError{o["upload_error"]=["domain":e.domain,"code":e.code]};if let e=v.ubiquitousItemDownloadingError{o["download_error"]=["domain":e.domain,"code":e.code]}
 } catch {let e=error as NSError;o["query_error"]=["domain":e.domain,"code":e.code]}
 let data=try! JSONSerialization.data(withJSONObject:o,options:[.sortedKeys]);print(String(data:data,encoding:.utf8)!)
}
