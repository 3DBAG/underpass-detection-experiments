# underpass-detection-experiments


## Overview
### Rotterdam3d_underpass_extraction

This is a submodule (created by C.Moon) with the code for extracting underpasses (outer ceiling surfaces) from the 3D Rottedam and 3D Den Haag data. 

#### How to install the submodule (first time clone):

If you just cloned this repository and want to initialize the submodule, run:

```
git submodule update --init --recursive
```

#### How to update the submodule to the latest commit:

To update the submodule to the latest commit from its tracked branch, run:

```
git submodule update --remote --merge
```

After updating, commit the change in the main repository:

```
git add rotterdam3d_underpass_extraction
git commit -m "Update submodule to latest commit"
```

## Demo Areas (meeting 16 march)
Two tiles:

Weesperstraat, Amsterdam (3DBAG tile 10/434/716)
```
POLYGON ((122093.33100000000558794 485890.39699999999720603, 122593.33100000000558794 485890.39699999999720603, 122593.33100000000558794 486390.39699999999720603, 122093.33100000000558794 486390.39699999999720603, 122093.33100000000558794 485890.39699999999720603))
```

Beemsterstraat, Amsterdam (3DBAG tile 9/444/728)
```
POLYGON ((124593.33100000000558794 488890.39699999999720603, 125593.33100000000558794 488890.39699999999720603, 125593.33100000000558794 489890.39699999999720603, 124593.33100000000558794 489890.39699999999720603, 124593.33100000000558794 488890.39699999999720603))
```
