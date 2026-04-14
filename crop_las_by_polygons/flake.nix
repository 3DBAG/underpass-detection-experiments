{
  description = "Fast Zig point-in-polygon library with Python bindings";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      lib = nixpkgs.lib;
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = f: lib.genAttrs systems (system: f system);
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python312.withPackages (ps: with ps; [
            numpy
            matplotlib
            laspy
            lazrs
            shapely
            pyproj
          ]);
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.zig
              pkgs.zls
              python
            ];

            shellHook = ''
              export PYTHONPATH="$PWD/python${PYTHONPATH:+:$PYTHONPATH}"
            '';
          };
        });
    };
}
