{
  description = "wosarcher: modular, scriptable research pipeline";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?rev=0ad6f47ea4fe188f4bc8f0380f93ae8523337c6c"; # nixos-26.05 (10 jul 2026)
  };

  outputs =
    { nixpkgs, ... }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            pkgs.python313
            pkgs.uv
            pkgs.nodejs
            pkgs.pnpm
            # Report export: pandoc writes DOCX and Typst source; typst renders the PDF.
            pkgs.pandoc
            pkgs.typst
          ];

          env = {
            # uv must use the Nix Python: downloaded Python builds do not run
            # on NixOS without extra setup.
            UV_PYTHON = "${pkgs.python313}/bin/python3";
            UV_PYTHON_DOWNLOADS = "never";
          };
        };
      });

      formatter = forAllSystems (pkgs: pkgs.nixfmt);
    };
}
