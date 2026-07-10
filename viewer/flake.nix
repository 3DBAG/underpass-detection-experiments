{
  description = "Cesium 3D Tiles Viewer dev environment";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = f:
        nixpkgs.lib.genAttrs systems (system: f (import nixpkgs { inherit system; }));
      src = builtins.filterSource
        (path: type:
          let
            base = builtins.baseNameOf path;
          in
            base != ".git" &&
            base != "node_modules" &&
            base != "dist" &&
            base != "result")
        ./.;
    in {
      packages = forAllSystems (pkgs: {
        default = pkgs.writeShellApplication {
          name = "3dtiles-tester";
          runtimeInputs = [ pkgs.bun pkgs.coreutils ];
          text = ''
            src_path="${src}"
            src_id="$(basename "$src_path")"
            cache_root="''${XDG_CACHE_HOME:-$HOME/.cache}/3dtiles-tester"
            app_dir="$cache_root/$src_id"
            mkdir -p "$cache_root"

            if [ ! -d "$app_dir" ]; then
              cp -R "$src_path" "$app_dir"
              chmod -R u+w "$app_dir"
            fi

            if [ ! -d "$app_dir/node_modules" ] || [ ! -f "$app_dir/dist/index.html" ]; then
              (
                cd "$app_dir"
                bun install --frozen-lockfile
                bun run build
              )
            fi

            exec bun "$app_dir/cli.ts" "$@"
          '';
        };
      });

      apps = forAllSystems (pkgs: {
        default = {
          type = "app";
          program = "${self.packages.${pkgs.stdenv.hostPlatform.system}.default}/bin/3dtiles-tester";
        };
      });

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [ pkgs.bun ];
          shellHook = ''
            echo "3dtiles-tester dev shell — bun $(bun --version)"
          '';
        };
      });
    };
}
