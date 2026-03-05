# underpass-detection-experiments



# Rotterdam3d_underpass_extraction

This is a submodule (created by C.Moon) with the code for extracting underpasses (outer ceiling surfaces) from the 3D Rottedam and 3D Den Haag data. 

### How to install the submodule (first time clone):

If you just cloned this repository and want to initialize the submodule, run:

```
git submodule update --init --recursive
```

### How to update the submodule to the latest commit:

To update the submodule to the latest commit from its tracked branch, run:

```
git submodule update --remote --merge
```

After updating, commit the change in the main repository:

```
git add rotterdam3d_underpass_extraction
git commit -m "Update submodule to latest commit"
```