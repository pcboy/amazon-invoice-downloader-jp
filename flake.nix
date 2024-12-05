{
  description = "A basic flake with a shell";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  inputs.systems.url = "github:nix-systems/default";
  inputs.flake-utils = {
    url = "github:numtide/flake-utils";
    inputs.systems.follows = "systems";
  };

  outputs =
    { nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default =
          let
            buildInputs = with pkgs; [
              pkgs.python312Packages.venvShellHook
              playwright-driver.browsers
              python3Packages.playwright
              (pkgs.python312.withPackages (
                ps: with ps; [
                  venvShellHook
                  docopt
                  #playwright
                  greenlet
                ]
              ))
              pkgs.bashInteractive
            ];
          in
          pkgs.mkShell {
            venvDir = ".venv";
            packages = buildInputs;
            nativeBuildInputs = with pkgs; [
              playwright-driver.browsers
            ];
            postShellHook = ''
              export PLAYWRIGHT_BROWSERS_PATH=${pkgs.playwright-driver.browsers}
              export PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=true
              export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath buildInputs}:$LD_LIBRARY_PATH"
              export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib.outPath}/lib:$LD_LIBRARY_PATH"
            '';
          };
      }
    );
}
