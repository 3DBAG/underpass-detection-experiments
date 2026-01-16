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
          cmake
          pkg-config
        ];
        cppDeps = with pkgs; [
          # manifold - geometry processing library (from upstream flake)
          manifoldPkg
          tbb  # required by manifold-tbb
          assimp
          clipper2

          # CGAL - Computational Geometry Algorithms Library
          cgal

          # geogram - geometry processing library
          geogram

          # nlohmann_json - JSON library
          nlohmann_json

          # GDAL with features
          gdal
          sqlite
          postgresql
          geos

          # eigen3 - linear algebra library
          eigen

          # Rerun SDK - visualization library
          rerunSdk
          arrow-cpp
        ];

      in
      {
        # Development shell
        devShells.default = pkgs.mkShell {
          buildInputs = cppDeps ++ buildTools;

          # Environment variables
          GDAL_DATA = "${pkgs.gdal}/share/gdal";
          PROJ_LIB = "${pkgs.proj}/share/proj";
          # CMAKE_MODULE_PATH="${pkgs.geogram.dev}/lib/cmake";
          CMAKE_PREFIX_PATH="${manifoldPkg}/lib/cmake;${pkgs.clipper2}/lib/cmake";

          shellHook = ''
            echo "Entering development environment for test-3d-intersection"
            echo ""
            echo "Use these cmake flags for configuration:"
            echo "  cmake -DCMAKE_BUILD_TYPE=Release \\"
            echo "        -DCMAKE_MODULE_PATH=${pkgs.geogram.dev}/lib/cmake \\"
            echo "        -B build -S ."
            echo ""
            echo "And then to build the project:"
            echo "  cmake --build build"
          '';
        };

        # Package definition
        packages.default = pkgs.stdenv.mkDerivation {
          pname = "test-3d-intersection";
          version = "0.1.0";

          src = ./.;

          nativeBuildInputs = buildTools;

          buildInputs = cppDeps;

          # CMake configuration
          cmakeFlags = [
            "-DCMAKE_BUILD_TYPE=Release"
            "-DCMAKE_MODULE_PATH=${pkgs.geogram.dev}/lib/cmake"
            "-DCMAKE_PREFIX_PATH=${manifoldPkg}/lib/cmake;${pkgs.clipper2}/lib/cmake"
          ];

          meta = with pkgs.lib; {
            description = "A C++ project for 3D intersection testing";
            license = licenses.mit;
            platforms = platforms.linux ++ platforms.darwin;
          };
        };
      });
}
