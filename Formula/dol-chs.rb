class DolChs < Formula
  desc "Run the official Degrees of Lewdity Chinese localization in a browser"
  homepage "https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization"
  url "https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization/releases/download/v0.5.11.9-chs-1.0.0a/DoL-ModLoader-0.5.11.9-v2.101.1.zip"
  version "0.5.11.9-chs-1.0.0a"
  sha256 "928a1940a8dc5198ffb1c600b6f39e8e9b52f46f27017d46040e7569157de7f6"
  license all_of: ["CC-BY-NC-SA-4.0", "MIT"]

  livecheck do
    url :stable
    regex(/^v?(\d+(?:\.\d+)+-chs-\d+(?:\.\d+)+[abr])$/i)
    strategy :github_latest
  end

  depends_on "python@3.14"

  resource "official-i18n" do
    url "https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization/releases/download/v0.5.11.9-chs-1.0.0a/ModI18N-0.5.11.9-chs-1.0.0a.mod.zip",
        using: :nounzip
    sha256 "90439d4bbb917249d953ada643b512c34e95097cddd9765921ac6a030ebfd1fa"
  end

  resource "official-images" do
    url "https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization/releases/download/v0.5.11.9-chs-1.0.0a/GameOriginalImagePack-0.5.11.9.mod.zip",
        using: :nounzip
    sha256 "23f2ed879ec7a476b6a42d015b955da7aa2d4d2ada62983701968e7c5625090c"
  end

  def install
    pkgshare.install "Degrees of Lewdity.html" => "index.html"
    pkgshare.install "CREDITS.md", "LICENSE", "README.md"
    (pkgshare/"VERSION").write version.to_s
    (pkgshare/"mods").install resource("official-i18n").cached_download => "official-i18n.mod.zip"
    (pkgshare/"mods").install resource("official-images").cached_download => "official-images.mod.zip"

    server = Pathname(__dir__).parent/"libexec/dol_http_server.py"
    installed_server = libexec/"dol_http_server.py"
    installed_server.write server.read
    chmod 0755, installed_server
    bin.install_symlink installed_server => "dol-chs"
  end

  service do
    run [opt_bin/"dol-chs", "--no-open", "--bind", "127.0.0.1", "8000"]
    keep_alive true
    log_path var/"log/dol-chs.log"
    error_log_path var/"log/dol-chs.log"
  end

  def caveats
    <<~EOS
      This game contains adult content and is intended only for users aged 18 or older.
      It is distributed by upstream under CC BY-NC-SA 4.0 for non-commercial use.

      Browser saves belong to the exact origin. Keep the same host and port when
      returning to an existing save. The default URL is http://127.0.0.1:8000/.
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/dol-chs --version")

    port = free_port
    pid = spawn bin/"dol-chs", "--no-open", "--quiet", "--bind", "127.0.0.1", port.to_s
    begin
      headers = shell_output("curl --silent --head --retry 10 --retry-connrefused http://127.0.0.1:#{port}/")
      assert_match "200 OK", headers

      mod_list = shell_output("curl --silent http://127.0.0.1:#{port}/modList.json")
      assert_equal [
        "/__dol_mods__/0/official-i18n.mod.zip",
        "/__dol_mods__/1/official-images.mod.zip",
      ], JSON.parse(mod_list)
    ensure
      Process.kill("TERM", pid)
      Process.wait(pid)
    end
  end
end
