# Execute the code
## 1. Create folders with data
Create the following structure:

```text
3DBAG_UNDERPASS_HEIGHTS/
├── image/
│   └── 24_07251_f_rgb.jpg
├── import/
│   ├── calibrated_camera_parameters.txt
│   ├── calibrated_external_camera_parameters.txt
│   └── offset.xyz
├── src/
│   └── ...
├── template/
│   ├── gelderseplein_lod2.city.json
│   ├── gelderseplein_LOD22_walls.off
│   └── gelderseplein_original_LOD22.off
└── README.md

```

## 2. How to run:
Create a Python virtual environment and install the project requirements: then run the script:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then run with:

```bash
python3 src/stage_1/stage1_registration.py
```

