# NixOS VM test of nixosModules.default: the socket-activated service, the
# host `wosarcher` client on the group's socket, the `wosarcherd` wrapper for
# the service user, a data directory only the service user can read, declared
# profiles and hooks, and PDF export under the unit's sandbox. Runs without
# network: `--until load` calls no provider.
#
#   nix build .#checks.x86_64-linux.nixos
{ self, pkgs }:

let
  lan = {
    llm.model = "lan-model";
    llm.api_key_file = "/etc/wosarcher-llm-key";
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

      # Read by systemd alone.
      environment.etc."wosarcher.env" = {
        text = ''
          WOSARCHER_PROFILE=lan
        '';
        mode = "0400";
      };
      environment.etc."wosarcher-llm-key" = {
        text = "dummy-key";
        mode = "0400";
        user = "wosarcher";
      };

      services.wosarcher = {
        enable = true;
        autoStart = false;
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
    auth = f"{data}/config/wosarcher/auth.json"
    sock = "/run/wosarcher/api.sock"

    def alice(command):
        return machine.succeed(f"su - alice -c {json.dumps(command)}")

    machine.wait_for_unit("wosarcher.socket")

    with subtest("socket mode and group; the service waits for a connection"):
        mode = machine.succeed(f"stat -c '%a %U %G' {sock}").strip()
        assert mode == "660 wosarcher wosarcher", mode
        machine.fail("systemctl is-active wosarcher.service")

    with subtest("socket activation starts the service for a member"):
        listing = alice("wosarcher runs --json")
        assert json.loads(listing) == [], listing
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
        mode = machine.succeed(f"stat -c '%a %U' {profiles}/lan.toml").strip()
        assert mode == "600 wosarcher", mode
        hooks = machine.succeed(f"cat {data}/config/wosarcher/hooks.toml")
        assert hooks.count("[[on_finish]]") == 1, hooks
        assert "http://127.0.0.1:9/hook" in hooks, hooks

    with subtest("member client sees the daemon's profiles, never its secrets"):
        listing = alice("wosarcher profile list")
        assert "lan  (user)" in listing, listing
        shown = alice("wosarcher profile show lan")
        assert 'api_key = "***"' in shown, shown
        assert "dummy-key" not in shown, shown
        machine.fail("su - alice -c 'cat /etc/wosarcher-llm-key'")
        machine.fail("su - alice -c 'cat /etc/wosarcher.env'")

    with subtest("member cannot read the data directory"):
        machine.fail(f"su - alice -c 'ls {data}/config/wosarcher'")
        machine.fail(f"su - alice -c 'cat {auth}'")

    with subtest("member run is created by the daemon"):
        alice("echo '# Note' > note.md")
        cli_run = json.loads(alice("wosarcher run q --sources files --attach note.md --until load --json"))["run_id"]
        machine.succeed(f"test -d {data}/share/wosarcher/runs/{cli_run}/attachments")
        runs = json.loads(machine.succeed(f"curl -sf {api}/runs"))
        found = [run for run in runs if run["run_id"] == cli_run]
        assert found and found[0]["origin"] == "cli", runs

    with subtest("server run is visible to the member"):
        machine.succeed("echo '# Server note' > /tmp/server-note.md")
        created = json.loads(machine.succeed(
            f"curl -sf -F attachments=@/tmp/server-note.md -F 'request={{\"query\": \"q\", \"sources\": \"files\", \"until\": \"load\"}}' {api}/runs"
        ))
        server_run = created["run_id"]
        machine.wait_until_succeeds(f"su - alice -c 'wosarcher runs --json' | grep -q {server_run}")

    with subtest("PDF export under the unit's sandbox, downloaded by the member"):
        report = {"body": "Hello.", "markdown": "# Report\n\nHello.", "cited": [], "references": []}
        target = f"{data}/share/wosarcher/runs/{cli_run}/report.json"
        machine.succeed(f"cat > {target} <<'EOF'\n{json.dumps(report)}\nEOF")
        machine.succeed(f"chown wosarcher:wosarcher {target} && chmod 0600 {target}")
        alice(f"wosarcher export {cli_run} --format pdf --output report.pdf")
        alice("head -c 5 report.pdf | grep -q '%PDF-'")

    with subtest("server deletes a member's run"):
        status = machine.succeed(f"curl -s -o /dev/null -w '%{{http_code}}' -X DELETE {api}/runs/{cli_run}")
        assert status == "204", status
        machine.succeed(f"test ! -e {data}/share/wosarcher/runs/{cli_run}")

    with subtest("the service user sets the password; auth.json stays 0600"):
        machine.succeed("printf 'hunter22\\nhunter22\\n' | sudo -u wosarcher setsid -w wosarcherd auth set-password")
        mode = machine.succeed(f"stat -c '%a %U' {auth}").strip()
        assert mode == "600 wosarcher", mode
        status = machine.succeed(f"curl -s -o /dev/null -w '%{{http_code}}' {api}/runs")
        assert status == "401", status
        machine.succeed(
            f"curl -sf -H 'Origin: https://wosarcher.example' -c /tmp/cookies "
            f"-H 'content-type: application/json' -d '{{\"password\": \"hunter22\"}}' {api}/login"
        )
        token = alice("wosarcher tokens new laptop").strip().splitlines()[-1]
        assert token.startswith("wosarcher_"), token
        session = machine.succeed(f"curl -sf -H 'Authorization: Bearer {token}' {api}/session")
        assert '"token"' in session, session
        mode = machine.succeed(f"stat -c '%a %U' {auth}").strip()
        assert mode == "600 wosarcher", mode
        assert "laptop" in alice("wosarcher tokens list")

    with subtest("other users are kept out"):
        out = machine.succeed("su - bob -c 'wosarcher runs; echo code=$?' 2>&1")
        assert "code=69" in out and sock in out, out
        machine.fail(f"su - bob -c 'ls {data}'")

    with subtest("dropped profile is removed, hand-made one kept"):
        machine.succeed(f"printf '[llm]\\nmodel = \"mine\"\\n' > {profiles}/mine.toml")
        machine.succeed("/run/current-system/specialisation/dropped/bin/switch-to-configuration test")
        alice("wosarcher runs")
        machine.wait_for_unit("wosarcher.service")
        machine.succeed(f"test ! -e {profiles}/old.toml")
        machine.succeed(f"test -f {profiles}/lan.toml")
        machine.succeed(f"test -f {profiles}/mine.toml")
        machine.succeed(f"test ! -e {data}/config/wosarcher/hooks.toml")
  '';
}
