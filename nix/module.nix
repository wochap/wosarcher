# services.wosarcher: the daemon as a native systemd unit with a Unix socket
# for the members of the `wosarcher` group, a host `wosarcher` client that
# talks to that socket, and a `wosarcherd` wrapper for administration as the
# service user. Only the service user can read the data directory.
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
  providersDir = "${configDir}/providers";
  depthsDir = "${configDir}/depths";
  blocks = [
    "search"
    "fetch"
    "prefilter"
    "score"
    "llm"
  ];
  runtimeDir = "/run/wosarcher";
  socketPath = "${runtimeDir}/api.sock";

  # One set feeds the unit and the `wosarcherd` wrapper, so they cannot drift.
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
  # Paths relative to the profiles directory, as the manifest records them.
  entryFiles = lib.concatLists (
    lib.mapAttrsToList (
      block: entries:
      lib.mapAttrsToList (name: settings: {
        path = "../providers/${block}/${name}.toml";
        file = toml.generate "wosarcher-${block}-${name}.toml" settings;
      }) entries
    ) cfg.providers
  );
  depthFiles = lib.mapAttrsToList (name: settings: {
    path = "../depths/${name}.toml";
    file = toml.generate "wosarcher-depth-${name}.toml" settings;
  }) cfg.depths;
  hooksFile = toml.generate "wosarcher-hooks.toml" cfg.hooks;

  install = file: target: ''
    install -m 0600 -o wosarcher -g wosarcher ${file} ${lib.escapeShellArg target}
  '';

  # Declared files are copied, never linked into the Nix store. The manifest
  # (profile names, ../providers/<block>/<name>.toml, ../depths/<name>.toml,
  # and ../hooks.toml) records which files the module wrote, so a dropped
  # profile, entry, or preset, or emptied hooks, is removed while hand-made
  # files are left alone.
  syncFiles = pkgs.writeShellScript "wosarcher-sync-files" ''
    set -euo pipefail
    # Data written by older versions was group-readable; it is the service user's alone.
    chmod -R go-rwx ${lib.escapeShellArg dataDir}
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
    ${lib.concatMapStrings (
      dir: "install -d -m 0700 -o wosarcher -g wosarcher ${lib.escapeShellArg dir}\n"
    ) ([ depthsDir ] ++ map (block: "${providersDir}/${block}") (lib.attrNames cfg.providers))}
    ${lib.concatMapStrings (entry: ''
      ${install entry.file "${profilesDir}/${entry.path}"}
      echo ${lib.escapeShellArg entry.path} >> "$manifest"
    '') (entryFiles ++ depthFiles)}
    ${lib.optionalString (cfg.hooks != { }) ''
      ${install hooksFile "${configDir}/hooks.toml"}
      echo ../hooks.toml >> "$manifest"
    ''}
    chown wosarcher:wosarcher "$manifest"
    chmod 0600 "$manifest"
  '';

  # The client holds no secret: it only needs the socket. It carries the
  # package's zsh completion, without the unwrapped bin/wosarcher.
  client = pkgs.symlinkJoin {
    name = "wosarcher-client";
    paths = [
      (pkgs.writeShellApplication {
        name = "wosarcher";
        text = ''
          export WOSARCHER_SOCKET=${lib.escapeShellArg socketPath}
          exec ${lib.getExe' cfg.package "wosarcher"} "$@"
        '';
      })
    ];
    postBuild = ''
      mkdir -p $out/share/zsh/site-functions
      ln -s ${cfg.package}/share/zsh/site-functions/_wosarcher $out/share/zsh/site-functions/_wosarcher
    '';
  };

  # For the service user: `sudo -u wosarcher wosarcherd auth set-password`.
  daemon = pkgs.writeShellApplication {
    name = "wosarcherd";
    text = ''
      ${lib.concatStrings (
        lib.mapAttrsToList (name: value: ''
          export ${name}=${lib.escapeShellArg value}
        '') sharedEnvironment
      )}
      umask 0077
      exec ${lib.getExe' cfg.package "wosarcherd"} "$@"
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
        Extra environment variables for the service and the `wosarcherd`
        wrapper. Never put secrets here: the values land in the Nix store.
        Use environmentFile instead.
      '';
    };

    environmentFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      example = "/run/secrets/wosarcher.env";
      description = ''
        File of NAME=value lines systemd reads at service start, for
        variables that must not land in the Nix store. Give it a path outside
        the Nix store; it may be readable by root alone (for example 0400
        root:root). No wrapper reads it. For secrets prefer the <x>_file
        settings in a provider entry (for example api_key_file =
        "/run/secrets/llm" in an llm entry), with the file readable by the
        wosarcher user.
      '';
    };

    profiles = lib.mkOption {
      type = lib.types.attrsOf toml.type;
      default = { };
      description = ''
        Profiles copied to /var/lib/wosarcher/config/wosarcher/profiles/<name>.toml
        before the service starts. A profile names one provider entry per
        block (`use.score = "jev-strict"`) and sets only its own keys
        (llm.model, the domain lists, search.language, and keys outside the
        provider blocks). A profile removed from this option is removed from
        the directory; hand-made profiles are kept. Never put secret values
        here: they land in the Nix store; auth.password_hash_file takes the
        path of a file instead.
      '';
    };

    providers = lib.mkOption {
      type = lib.types.attrsOf (lib.types.attrsOf toml.type);
      default = { };
      example = lib.literalExpression ''
        {
          score.jev-strict = {
            provider = "jev";
            base_url = "https://api.typesafe.ai/v1";
            api_key_file = "/run/secrets/typesafe";
            min_score = 2.0;
          };
          llm.omniroute = {
            provider = "openai";
            base_url = "http://ssc:20700/v1";
            api_key_file = "/run/secrets/omniroute";
            model = "research-smart";
            models.research-smart = { context_window = 1048576; max_output_tokens = 131072; };
          };
        }
      '';
      description = ''
        Provider entries by block (search, fetch, prefilter, score, llm) and
        name, copied to
        /var/lib/wosarcher/config/wosarcher/providers/<block>/<name>.toml
        before the service starts. An entry holds that block's fields at the
        top level; an llm entry may list per-model limits under `models`.
        An entry removed from this option is removed from the directory;
        hand-made entries are kept. Never put secret values here: they land
        in the Nix store. Pass a secret with the <x>_file settings, for
        example api_key_file = "/run/secrets/llm" in an llm entry: the entry
        holds the path of a file readable by the wosarcher user, never the
        value.
      '';
    };

    depths = lib.mkOption {
      type = lib.types.attrsOf toml.type;
      default = { };
      description = ''
        User depth presets copied to
        /var/lib/wosarcher/config/wosarcher/depths/<name>.toml before the
        service starts, listed after the built-in presets. A name may not be
        a built-in preset's (quick, standard, deep, exhaustive) or custom.
        A preset removed from this option is removed from the directory.
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
        Users added to the wosarcher group, which grants access to the
        daemon's socket (${socketPath}) and nothing else: members run the host
        `wosarcher` client against the daemon, and cannot read its data
        directory, profiles, or secrets.
      '';
    };

    autoStart = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = ''
        Start the service at boot. When false, the service starts on the
        first connection to its socket (wosarcher.socket) or through a socket
        proxy.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = map (block: {
      assertion = lib.elem block blocks;
      message = "services.wosarcher.providers.${block}: not a block; use ${lib.concatStringsSep ", " blocks}";
    }) (lib.attrNames cfg.providers);

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

    # The runtime directory lets the group reach the socket; the data
    # directories are the service user's alone.
    systemd.tmpfiles.rules = [
      "d ${runtimeDir} 0750 wosarcher wosarcher -"
    ]
    ++ map (dir: "d ${dir} 0700 wosarcher wosarcher -") [
      dataDir
      "${dataDir}/config"
      configDir
      profilesDir
      providersDir
      depthsDir
      "${dataDir}/share"
      "${dataDir}/cache"
    ];

    environment.systemPackages = [
      client
      daemon
    ];

    systemd.sockets.wosarcher = {
      description = "wosarcher API socket";
      wantedBy = [ "sockets.target" ];
      listenStreams = [ socketPath ];
      socketConfig = {
        SocketMode = "0660";
        SocketUser = "wosarcher";
        SocketGroup = "wosarcher";
      };
    };

    systemd.services.wosarcher = {
      description = "wosarcher research server";
      wantedBy = lib.mkIf cfg.autoStart [ "multi-user.target" ];
      requires = [ "wosarcher.socket" ];
      after = [
        "network.target"
        "wosarcher.socket"
      ];
      environment = sharedEnvironment // {
        PYTHONUNBUFFERED = "1";
      };
      serviceConfig = {
        ExecStartPre = "+${syncFiles}";
        ExecStart = lib.escapeShellArgs [
          (lib.getExe' cfg.package "wosarcherd")
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
        StateDirectoryMode = "0700";
        UMask = "0077";
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
        ReadWritePaths = [
          dataDir
          runtimeDir
        ];
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
