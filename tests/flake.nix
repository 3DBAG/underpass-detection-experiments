{
  description = "Underpass street-lidar height pipeline shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { nixpkgs, ... }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          py = pkgs.python312Packages;
          projData = pkgs.runCommand "underpass-proj-data" { } ''
            mkdir -p "$out/share/proj"
            cp -a ${pkgs.proj}/share/proj/. "$out/share/proj/"
            chmod -R u+w "$out/share/proj"
            if [ ! -e "$out/share/proj/nl_nsgi_nlgeo2018.tif" ]; then
              cp ${pkgs.fetchurl {
                url = "https://cdn.proj.org/nl_nsgi_nlgeo2018.tif";
                hash = "sha256-+OMsVr+JQPw/77wOQT60VGYz7VmLZpxjhWzd+DKJksA=";
              }} "$out/share/proj/nl_nsgi_nlgeo2018.tif"
            fi
            if [ ! -e "$out/share/proj/nl_nsgi_rdtrans2018.tif" ]; then
              cp ${pkgs.fetchurl {
                url = "https://cdn.proj.org/nl_nsgi_rdtrans2018.tif";
                hash = "sha256-dlODEZG0JOcVqQZGiWL8YAcc+3GjGGsqWPCYuri/Qd4=";
              }} "$out/share/proj/nl_nsgi_rdtrans2018.tif"
            fi
          '';
          pyprojSiteCustomize = pkgs.writeTextDir "sitecustomize.py" ''
            import os

            proj_data = os.environ.get("PROJ_DATA")
            if proj_data:
                from pyproj import datadir

                datadir.set_data_dir(proj_data)
          '';
          py3dtilesWithLas = py.py3dtiles.overridePythonAttrs (old: {
            dependencies = (old.dependencies or [ ]) ++ [ py.laspy ];
            patches = (old.patches or [ ]) ++ [
              ./patches/py3dtiles-12.1.1-point-glb-zup-and-dummynode.patch
            ];
            doCheck = false;
            doInstallCheck = false;
          });
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.python312
              py.laspy
              py.lazrs
              py.matplotlib
              py.numpy
              py.psycopg
              py.shapely
              py3dtilesWithLas
              pkgs.proj
              pkgs.uv
              pkgs.zig
              pkgs.zls
              pkgs.postgresql
            ];

            PROJ_DATA = "${projData}/share/proj";

            shellHook = ''
              REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
              export PYTHONPATH="${pyprojSiteCustomize}:$REPO_ROOT/crop_las_by_polygons/scripts:$REPO_ROOT/crop_las_by_polygons/python:$REPO_ROOT/height_from_streetlidar''${PYTHONPATH:+:$PYTHONPATH}"
              if [ "$(uname -s)" = "Darwin" ]; then
                export ZIGPIP_LIB="$REPO_ROOT/crop_las_by_polygons/zig-out/lib/libzigpip.dylib"
              else
                export ZIGPIP_LIB="$REPO_ROOT/crop_las_by_polygons/zig-out/lib/libzigpip.so"
              fi
            '';
          };
        });
    };
}
