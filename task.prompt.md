`syncript sync --reset` command has bug. Sample output:

```
PS C:\Users\bs\projects\jibit\cloud\ipg-commons> syncript sync --reset -v
[config] Using C:\Users\bs\projects\jibit\cloud\ipg-commons\.syncript

================================================================
  Sync  C:\Users\bs\projects\jibit\cloud\ipg-commons
   ↔   root@23.27.125.40:9011:/root/projects/jibit/cloud/ipg-commons
================================================================

[01:32:05] [ignore] 33 pattern(s) loaded from ./.stignore
Sync state and progress have been reset. Starting a new sync operation from scratch...
[01:32:05] [SSH] connecting to root@23.27.125.40:9011 …
[01:32:05] [SSH] using SOCKS proxy socks5://localhost:10808
[01:32:08] [SSH] connected ✓
[01:32:08] [remote] Ensuring remote root exists: /root/projects/jibit/cloud/ipg-commons
[01:32:09] [remote] ensured remote root exists: /root/projects/jibit/cloud/ipg-commons
[01:32:09] [scan] Firing remote scan → /tmp/sync_scan_a35b9321c5ba48739b9de9be6d0d328e.tsv.gz (marker: /tmp/sync_scan_a35b9321c5ba48739b9de9be6d0d328e.done)
[01:32:09] [scan] Scanning local files …
[01:32:10] [scan] 222 local file(s) found
[01:32:10] [scan] Waiting for remote scan (poll every 5s, timeout 120s) …
[01:32:10] [scan] Polling for remote scan marker /tmp/sync_scan_a35b9321c5ba48739b9de9be6d0d328e.done …
[01:32:11] 
[scan] Remote scan complete.
[01:32:13] [scan] 222 remote file(s) after filtering
[01:32:13] [plan] push=222  pull=0  del_remote=0  del_local=0  conflicts=0  (total=222)

[01:32:13] [push] Pushing 222 file(s) (target ≤ 512 KB compressed per batch) …
[01:32:13] [push] Batch 1: 222 file(s)
[01:32:13]   [PUSH] packing 222 file(s) into tmpnr3k99i6.tar.gz …
[01:32:13]   [PUSH] packed → 137 KB
[01:32:13]   [PUSH] uploading tmpnr3k99i6.tar.gz → remote …
[01:32:14]   [PUSH] extracting on remote …
[01:32:15] ⚠  Sync failed: 'pushed'
Traceback (most recent call last):
  File "C:\\Users\\bs\\projects\\personal\\syncript\syncript\core\sync_engine.py", line 371, in run_sync
    compressed, uncompressed = push_batch(mgr, batch, dry_run, state, progress)
                               ~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\\Users\\bs\\projects\\personal\\syncript\syncript\operations\transfer.py", line 69, in push_batch
    prog["pushed"].append(rel)
    ~~~~^^^^^^^^^^
KeyError: 'pushed'
[01:32:15] ⚠  Progress saved — next run will resume from last checkpoint.
[01:32:15] [cleanup] removed remote scan file /tmp/sync_scan_a35b9321c5ba48739b9de9be6d0d328e.done
[01:32:15] [SSH] disconnected.
```
