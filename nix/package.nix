# The wosarcher client and the wosarcherd daemon: a virtual environment built
# by uv2nix from uv.lock (PyPI wheels, runtime dependencies only). The daemon
# gets pandoc and typst on PATH for report export and the built web UI as the
# default static directory.
{
  lib,
  callPackage,
  python313,
  makeWrapper,
  runCommand,
  pandoc,
  typst,
  pyproject-nix,
  uv2nix,
  pyproject-build-systems,
}:

let
  workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ../.; };

  pythonSet =
    (callPackage pyproject-nix.build.packages { python = python313; }).overrideScope
      (
        lib.composeManyExtensions [
          pyproject-build-systems.overlays.wheel
          (workspace.mkPyprojectOverlay { sourcePreference = "wheel"; })
        ]
      );

  venv = pythonSet.mkVirtualEnv "wosarcher-env" workspace.deps.default;

  web = callPackage ./web.nix { };
in
runCommand "wosarcher-0.1.0"
  {
    nativeBuildInputs = [ makeWrapper ];
    passthru = { inherit venv web; };
    meta.mainProgram = "wosarcher";
  }
  ''
    makeWrapper ${venv}/bin/wosarcher $out/bin/wosarcher
    makeWrapper ${venv}/bin/wosarcherd $out/bin/wosarcherd \
      --prefix PATH : ${
        lib.makeBinPath [
          pandoc
          typst
        ]
      } \
      --set-default WOSARCHER_SERVER__STATIC_DIR ${web}
  ''
