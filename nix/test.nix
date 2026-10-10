# NixOS VM test of nixosModules.default: the service, the shared data
# directory, the host CLI wrapper, declared profiles and hooks, auth.json
# shared between the service and a group member, and PDF export under the
# unit's sandbox. Runs without network: `--until load` calls no provider.
#
#   nix build .#checks.x86_64-linux.nixos
{ self, pkgs }:

let
  lan = {
    llm.model = "lan-model";
  };
in
pkgs.testers.runNixOSTest {
  name = "wosarcher";

  nodes.machine =
    { lib, pkgs, ... }:
    {
      imports = [ self.nixosModules.default ];

      users.users.alice.isNormalUser = true;
      users.users.bob.isNormalUser = true;

      environment.systemPackages = [ pkgs.curl ];

      # A sops template would be 0440 root:wosarcher too.
      environment.etc."wosarcher.env" = {
        text = ''
          WOSARCHER_LLM__API_KEY=dummy-key
          WOSARCHER_PROFILE=lan
        '';
        mode = "0440";
        group = "wosarcher";
      };

      services.wosarcher = {
        enable = true;
        users = [ "alice" ];
        allowedOrigins = [ "https://wosarcher.example" ];
        environmentFile = "/etc/wosarcher.env";
        profiles = {
          inherit lan;
          old.llm.model = "old-model";
        };
        hooks.on_finish = [ { url = "http://127.0.0.1:9/hook"; } ];
      };

      specialisation.dropped.configuration = {
        services.wosarcher.profiles = lib.mkForce { inherit lan; };
        services.wosarcher.hooks = lib.mkForce { };
      };
    };

  testScript = ''
    import json

    api = "http://127.0.0.1:8765/api"
    data = "/var/lib/wosarcher"
    profiles = f"{data}/config/wosarcher/profiles"

    def alice(command):
        return machine.succeed(f"su - alice -c {json.dumps(command)}")

    machine.wait_for_unit("wosarcher.service")
    machine.wait_for_open_port(8765)

    with subtest("service runs as wosarcher and answers"):
        user = machine.succeed("systemctl show -p User --value wosarcher.service").strip()
        assert user == "wosarcher", user
        pid = machine.succeed("systemctl show -p MainPID --value wosarcher.service").strip()
        machine.succeed(f"test $(stat -c %U /proc/{pid}) = wosarcher")
        machine.succeed(f"curl -sf {api}/session")
        machine.succeed("curl -sf http://127.0.0.1:8765/ | grep -q '<title>wosarcher</title>'")

    with subtest("declared profile and hooks"):
        machine.succeed(f"test -f {profiles}/lan.toml && test ! -L {profiles}/lan.toml")
        machine.succeed(f"test $(stat -c %G {profiles}/lan.toml) = wosarcher")
        hooks = machine.succeed(f"cat {data}/config/wosarcher/hooks.toml")
        assert hooks.count("[[on_finish]]") == 1, hooks
        assert "http://127.0.0.1:9/hook" in hooks, hooks

    with subtest("member CLI uses the server's profiles and secrets"):
        listing = alice("wosarcher profile list")
        assert "lan  (user)" in listing, listing
        shown = alice("wosarcher profile show")
        assert 'api_key = "***"' in shown, shown
        assert "dummy-key" not in shown, shown

    with subtest("member CLI run is visible to the server"):
        alice("echo '# Note' > note.md")
        cli_run = json.loads(alice("wosarcher run q --sources files --attach note.md --until load --json"))["run_id"]
        machine.succeed(f"test -d {data}/share/wosarcher/runs/{cli_run}")
        runs = machine.succeed(f"curl -sf {api}/runs")
        assert cli_run in runs, runs

    with subtest("server run is visible to the member"):
        machine.succeed("echo '# Server note' > /tmp/server-note.md")
        created = json.loads(machine.succeed(
            f"curl -sf -F attachments=@/tmp/server-note.md -F 'request={{\"query\": \"q\", \"sources\": \"files\", \"until\": \"load\"}}' {api}/runs"
        ))
        server_run = created["run_id"]
        machine.wait_until_succeeds(f"test -f {data}/share/wosarcher/runs/{server_run}/request.json")
        machine.wait_until_succeeds(f"su - alice -c 'wosarcher runs --json' | grep -q {server_run}")

    with subtest("PDF export under the unit's sandbox"):
        report = {"body": "Hello.", "markdown": "# Report\n\nHello.", "cited": [], "references": []}
        machine.succeed(f"cat > /tmp/report.json <<'EOF'\n{json.dumps(report)}\nEOF")
        alice(f"cp /tmp/report.json {data}/share/wosarcher/runs/{cli_run}/report.json")
        machine.succeed(f"curl -sf -o /tmp/report.pdf '{api}/runs/{cli_run}/export?format=pdf'")
        machine.succeed("head -c 5 /tmp/report.pdf | grep -q '%PDF-'")

    with subtest("server deletes a member's run"):
        status = machine.succeed(f"curl -s -o /dev/null -w '%{{http_code}}' -X DELETE {api}/runs/{cli_run}")
        assert status == "204", status
        machine.succeed(f"test ! -e {data}/share/wosarcher/runs/{cli_run}")

    with subtest("auth.json is shared by the member and the server"):
        alice("printf 'hunter22\\nhunter22\\n' | wosarcher auth set-password")
        auth = f"{data}/config/wosarcher/auth.json"
        mode = machine.succeed(f"stat -c '%a %G' {auth}").strip()
        assert mode == "660 wosarcher", mode
        machine.succeed(
            f"curl -sf -H 'Origin: https://wosarcher.example' -c /tmp/cookies "
            f"-H 'content-type: application/json' -d '{{\"password\": \"hunter22\"}}' {api}/login"
        )
        token = json.loads(machine.succeed(
            f"curl -sf -b /tmp/cookies -H 'content-type: application/json' -d '{{\"name\": \"t\"}}' {api}/tokens"
        ))["token"]
        session = machine.succeed(f"curl -sf -H 'Authorization: Bearer {token}' {api}/session")
        assert '"token"' in session, session
        alice("printf 'hunter33\\nhunter33\\n' | wosarcher auth set-password")
        mode = machine.succeed(f"stat -c '%a %G' {auth}").strip()
        assert mode == "660 wosarcher", mode

    with subtest("other users are kept out"):
        out = machine.fail("su - bob -c 'wosarcher runs' 2>&1")
        assert "/etc/wosarcher.env" in out and "wosarcher" in out, out
        machine.fail(f"su - bob -c 'ls {data}'")

    with subtest("dropped profile is removed, hand-made one kept"):
        machine.succeed(f"printf '[llm]\\nmodel = \"mine\"\\n' > {profiles}/mine.toml")
        machine.succeed("/run/current-system/specialisation/dropped/bin/switch-to-configuration test")
        machine.wait_for_unit("wosarcher.service")
        machine.succeed(f"test ! -e {profiles}/old.toml")
        machine.succeed(f"test -f {profiles}/lan.toml")
        machine.succeed(f"test -f {profiles}/mine.toml")
        machine.succeed(f"test ! -e {data}/config/wosarcher/hooks.toml")
  '';
}
