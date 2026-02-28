{
  description = "A C++ project for 3D intersection testing";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    manifold.url = "github:elalish/manifold";
  };

  outputs = { self, nixpkgs, flake-utils, manifold }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        manifoldPkg = manifold.packages.${system}.manifold-tbb;

        # Rerun SDK derivation
        rerunSdk = pkgs.stdenv.mkDerivation {
          pname = "rerun-sdk";
          version = "0.28.2";
          src = pkgs.fetchurl {
            url = "https://github.com/rerun-io/rerun/releases/download/0.28.2/rerun_cpp_sdk.zip";
            sha256 = "c69d639257eb00e6385e74729f811378abb68c06ab2fad7dba355cedfff1c31b";
          };
          nativeBuildInputs = [ pkgs.unzip pkgs.cmake ];
          buildInputs = [ pkgs.arrow-cpp ];
          cmakeFlags = [
            "-DRERUN_DOWNLOAD_AND_BUILD_ARROW=OFF"
          ];
        };

        # Development dependencies matching vcpkg.json
        buildTools = with pkgs; [
          zig
        ];
        cppDeps = with pkgs; [
          manifoldPkg
          tbb  # required by manifold-tbb
          assimp
          clipper2

          # CGAL - Computational Geometry Algorithms Library
          cgal
          gmp
          mpfr
          boost
          eigen

          # geogram - geometry processing library
          geogram

          # GDAL with features
          gdal
          sqlite
          postgresql
          geos

          # Rerun SDK - visualization library
          rerunSdk
          arrow-cpp
        ];

      in
      {
        # Development shell
        devShells.default = pkgs.mkShell {
          buildInputs = cppDeps ++ buildTools ++ [ pkgs.wget pkgs.just ];

          # Environment variables
          GDAL_DATA = "${pkgs.gdal}/share/gdal";
          PROJ_LIB = "${pkgs.proj}/share/proj";
          # CMAKE_MODULE_PATH="${pkgs.geogram.dev}/lib/cmake";
          # CMAKE_PREFIX_PATH="${manifoldPkg}/lib/cmake;${pkgs.clipper2}/lib/cmake";

          shellHook = ''
            export NIX_CFLAGS_COMPILE=$(echo "$NIX_CFLAGS_COMPILE" | sed 's/-fmacro-prefix-map=[^ ]*//g')
            echo "Entering development environment for add_underpass"
            echo ""
            echo "To download 3dbag CityJSON test tile (id 9-444-728):"
            echo "  just download-tile"
            echo ""
            echo "To build the project run:"
            echo "  zig build"
            echo ""
            echo "  (To compile in release mode add: -Doptimize=ReleaseFast)"
            echo ""
            echo "To run the program with sample data:"
            echo "  ./zig-out/bin/add_underpass ./sample_data/amsterdam_beemsterstraat_42.gpkg ./sample_data/9-444-728.city.json out.ply hoogte identificatie manifold"
            echo ""
            echo "  (a number of .ply files will appear in the current working directory)"
          '';
        };

        # Package definition
        packages.default = pkgs.stdenv.mkDerivation {
          pname = "add-underpass";
          version = "0.1.0";

          src = ./.;

          nativeBuildInputs = [ pkgs.zig ];

          buildInputs = cppDeps;

          # Don't run cmake configure
          dontConfigure = true;

          buildPhase = ''
            runHook preBuild
            # Filter out unsupported flags for Zig
            export NIX_CFLAGS_COMPILE=$(echo "$NIX_CFLAGS_COMPILE" | sed 's/-fmacro-prefix-map=[^ ]*//g')
            export HOME=$TMPDIR
            export XDG_CACHE_HOME=$TMPDIR/.cache
            zig build -Doptimize=ReleaseFast
            runHook postBuild
          '';

          installPhase = ''
            runHook preInstall
            mkdir -p $out/bin
            cp zig-out/bin/add_underpass $out/bin/
            runHook postInstall
          '';

          meta = with pkgs.lib; {
            description = "A C++ project for 3D intersection testing";
            license = licenses.mit;
            platforms = platforms.linux ++ platforms.darwin;
          };
        };
      });
}
