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
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.python312
              py.laspy
              py.lazrs
              py.numpy
              py.psycopg
              py.shapely
              pkgs.zig
              pkgs.zls
              pkgs.postgresql
            ];

            shellHook = ''
              REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
              export PYTHONPATH="$REPO_ROOT/crop_las_by_polygons/scripts:$REPO_ROOT/crop_las_by_polygons/python:$REPO_ROOT/height_from_streetlidar''${PYTHONPATH:+:$PYTHONPATH}"
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
