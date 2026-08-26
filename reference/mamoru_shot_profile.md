# Mamoru Manhwa — measured shot behaviour

Source: `mamoru_fp_video.mp4`, window 300s + 1200s.
Scene-cut detection via ffmpeg `select='gt(scene,T)'`; a recap video is a
slideshow with pan/zoom, so T separates panel changes from camera drift.

| threshold | shots | cuts/min | median | mean | p10 | p90 | <1.5s | <1s | >6s | longest |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.2 | 326 | 16.3 | 2.87s | 3.68s | 0.95s | 7.62s | 22.1% | 10.4% | 17.5% | 16.37s |
| 0.3 | 325 | 16.25 | 2.87s | 3.69s | 0.95s | 7.62s | 22.2% | 10.5% | 17.8% | 16.37s |
| 0.4 | 314 | 15.65 | 2.97s | 3.82s | 0.98s | 7.77s | 21.3% | 10.2% | 19.7% | 16.37s |
