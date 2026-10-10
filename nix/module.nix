# services.wosarcher: the server as a native systemd unit, plus a host
# `wosarcher` CLI that shares its profiles, runs, caches, and secrets with
# the members of the `wosarcher` group.
self:
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.wosarcher;
  toml = pkgs.formats.toml { };

  dataDir = "/var/lib/wosarcher";
  configDir = "${dataDir}/config/wosarcher";
  profilesDir = "${configDir}/profiles";

  # One set feeds the unit and the CLI wrapper, so they cannot drift.
  sharedEnvironment = {
    XDG_CONFIG_HOME = "${dataDir}/config";
    XDG_DATA_HOME = "${dataDir}/share";
    XDG_CACHE_HOME = "${dataDir}/cache";
  }
  // lib.optionalAttrs (cfg.allowedOrigins != [ ]) {
    WOSARCHER_AUTH__ALLOWED_ORIGINS = builtins.toJSON cfg.allowedOrigins;
  }
  // cfg.environment;

  profileFiles = lib.mapAttrs (name: settings: toml.generate "wosarcher-${name}.toml" settings) cfg.profiles;
  hooksFile = toml.generate "wosarcher-hooks.toml" cfg.hooks;

  install = file: target: ''
    install -m 0640 -o wosarcher -g wosarcher ${file} ${lib.escapeShellArg target}
  '';

  # Declared files are copied, never linked into the Nix store. The manifest
  # (profile names, and ../hooks.toml) records which files the module wrote,
  # so a dropped profile or emptied hooks is removed while hand-made files are
  # left alone.
  syncFiles = pkgs.writeShellScript "wosarcher-sync-files" ''
    set -euo pipefail
    manifest=${lib.escapeShellArg "${profilesDir}/.nix-managed"}
    if [ -f "$manifest" ]; then
      while IFS= read -r name; do
        [ -n "$name" ] && rm -f ${lib.escapeShellArg profilesDir}/"$name"
      done < "$manifest"
    fi
    : > "$manifest"
    ${lib.concatStrings (
      lib.mapAttrsToList (name: file: ''
        ${install file "${profilesDir}/${name}.toml"}
        echo ${lib.escapeShellArg "${name}.toml"} >> "$manifest"
      '') profileFiles
    )}
    ${lib.optionalString (cfg.hooks != { }) ''
      ${install hooksFile "${configDir}/hooks.toml"}
      echo ../hooks.toml >> "$manifest"
    ''}
    chown wosarcher:wosarcher "$manifest"
    chmod 0660 "$manifest"
  '';

  wrapper = pkgs.writeShellApplication {
    name = "wosarcher";
    text = ''
      ${lib.concatStrings (
        lib.mapAttrsToList (name: value: ''
          export ${name}=${lib.escapeShellArg value}
        '') sharedEnvironment
      )}
      ${lib.optionalString (cfg.environmentFile != null) ''
        env_file=${lib.escapeShellArg (toString cfg.environmentFile)}
        if [ ! -r "$env_file" ]; then
          echo "wosarcher: cannot read $env_file; add your user to services.wosarcher.users (group wosarcher)" >&2
          exit 2
        fi
        set -a
        # shellcheck disable=SC1090
        . "$env_file"
        set +a
      ''}
      umask 0007
      exec ${lib.getExe cfg.package} "$@"
    '';
  };
in
{
  options.services.wosarcher = {
    enable = lib.mkEnableOption "the wosarcher research server";

    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.wosarcher;
      defaultText = lib.literalExpression "wosarcher.packages.\${system}.wosarcher";
      description = "The wosarcher package.";
    };

    host = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1";
      description = "Address the server binds to.";
    };

    port = lib.mkOption {
      type = lib.types.port;
      default = 8765;
      description = "Port the server listens on.";
    };

    allowedOrigins = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      example = [ "https://wosarcher.example" ];
      description = ''
        Browser origins allowed to send state-changing requests, passed as
        auth.allowed_origins. Needed when a reverse proxy serves the UI on
        another origin than the bind address.
      '';
    };

    environment = lib.mkOption {
      type = lib.types.attrsOf lib.types.str;
      default = { };
      example = {
        WOSARCHER_PROFILE = "lan";
      };
      description = ''
        Extra environment variables for the service and the CLI wrapper.
        Never put secrets here: the values land in the Nix store. Use
        environmentFile instead.
      '';
    };

    environmentFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      example = "/run/secrets/wosarcher.env";
      description = ''
        File of NAME=value lines read at service start and by the CLI
        wrapper, for secrets such as WOSARCHER_LLM__API_KEY or
        WOSARCHER_AUTH__PASSWORD_HASH. Give it a path outside the Nix store.
        The wrapper runs as the calling user, so the file must be readable by
        the wosarcher group (for example 0440 root:wosarcher); every member of
        the group can then read every secret in it.
      '';
    };

    profiles = lib.mkOption {
      type = lib.types.attrsOf toml.type;
      default = { };
      description = ''
        Profiles copied to /var/lib/wosarcher/config/wosarcher/profiles/<name>.toml
        before the service starts. A profile removed from this option is
        removed from the directory; hand-made profiles are kept. Never put
        secrets here: they land in the Nix store. Use environmentFile instead.
      '';
    };

    hooks = lib.mkOption {
      type = toml.type;
      default = { };
      description = ''
        Run hooks written to /var/lib/wosarcher/config/wosarcher/hooks.toml
        before the service starts; the file is removed when this is empty.
        Never put secrets here: they land in the Nix store.
      '';
    };

    users = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      description = ''
        Users added to the wosarcher group. Members can use the host
        `wosarcher` CLI against the server's profiles, runs, and caches, and
        can read every secret: the environment file and the session secret
        and password hash in auth.json.
      '';
    };

    autoStart = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = ''
        Start the service at boot. Set to false when a socket proxy starts it
        on demand.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    users.users = lib.mkMerge [
      {
        wosarcher = {
          isSystemUser = true;
          group = "wosarcher";
          home = dataDir;
        };
      }
      (lib.genAttrs cfg.users (_: {
        extraGroups = [ "wosarcher" ];
      }))
    ];
    users.groups.wosarcher = { };

    # setgid: directories created later inherit the group.
    systemd.tmpfiles.rules = map (dir: "d ${dir} 2770 wosarcher wosarcher -") [
      dataDir
      "${dataDir}/config"
      configDir
      profilesDir
      "${dataDir}/share"
      "${dataDir}/cache"
    ];

    environment.systemPackages = [ wrapper ];

    systemd.services.wosarcher = {
      description = "wosarcher research server";
      wantedBy = lib.mkIf cfg.autoStart [ "multi-user.target" ];
      after = [ "network.target" ];
      environment = sharedEnvironment // {
        PYTHONUNBUFFERED = "1";
      };
      serviceConfig = {
        ExecStartPre = "+${syncFiles}";
        ExecStart = lib.escapeShellArgs [
          (lib.getExe cfg.package)
          "serve"
          "--host"
          cfg.host
          "--port"
          (toString cfg.port)
        ];
        EnvironmentFile = lib.mkIf (cfg.environmentFile != null) cfg.environmentFile;
        User = "wosarcher";
        Group = "wosarcher";
        StateDirectory = "wosarcher";
        StateDirectoryMode = "2770";
        UMask = "0007";
        WorkingDirectory = dataDir;
        Restart = "on-failure";
        RestartSec = 2;
        # The server's 10-second run grace plus shutdown.
        TimeoutStopSec = 45;

        NoNewPrivileges = true;
        CapabilityBoundingSet = "";
        AmbientCapabilities = "";
        TasksMax = 512;
        ProtectSystem = "strict";
        ReadWritePaths = [ dataDir ];
        ProtectHome = true;
        PrivateTmp = true;
        PrivateDevices = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectKernelLogs = true;
        ProtectControlGroups = true;
        ProtectClock = true;
        ProtectHostname = true;
        RestrictNamespaces = true;
        RestrictRealtime = true;
        RestrictSUIDSGID = true;
        LockPersonality = true;
        RestrictAddressFamilies = [
          "AF_INET"
          "AF_INET6"
          "AF_UNIX"
        ];
        SystemCallFilter = [ "@system-service" ];
        SystemCallArchitectures = "native";
      };
    };
  };
}
