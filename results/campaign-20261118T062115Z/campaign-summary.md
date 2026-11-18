# Campaign summary

Runs: 9 | Jobs submitted: 48 | Complete and verified: 48

| Scenario | Rep | Jobs | Verified | Jobs per worker | Max queue (s) | Median turnaround (s) | Extra | OK |
|---|---|---|---|---|---|---|---|---|
| normal | 1 | 9 | 9 | worker:3 / worker2:3 / worker3:3 | 40.0 | 44.0 | even split | yes |
| normal | 2 | 9 | 9 | worker:3 / worker2:3 / worker3:3 | 40.0 | 44.0 | even split | yes |
| normal | 3 | 9 | 9 | worker:3 / worker2:3 / worker3:3 | 40.0 | 44.0 | even split | yes |
| fifo | 1 | 6 | 6 | worker2:5 / worker3:1 | 84.0 | 60.0 | FIFO order kept | yes |
| fifo | 2 | 6 | 6 | worker2:5 / worker3:1 | 83.0 | 60.5 | FIFO order kept | yes |
| fifo | 3 | 6 | 6 | worker2:6 | 80.0 | 58.0 | FIFO order kept | yes |
| recovery | 1 | 1 | 1 | worker2:1 / worker3:1 | 0.0 | 276.0 | recovery 146.672 s -> hpc-worker3 | yes |
| recovery | 2 | 1 | 1 | worker2:1 / worker3:1 | 0.0 | 272.0 | recovery 142.212 s -> hpc-worker3 | yes |
| recovery | 3 | 1 | 1 | worker2:1 / worker3:1 | 0.0 | 273.0 | recovery 142.963 s -> hpc-worker3 | yes |

Recovery time: median 143.0 s, min 142.212 s, max 146.672 s over 3 runs.
