// Brain for Mac: a native window around the local Brain server (bin/brain), with macOS blur behind the page.
// The page gets class "native" on <html>; the Mac glass theme then clears its background so the desktop shows through.
// Build: mac/build.sh → ~/Applications/Brain.app
import Cocoa
import WebKit

// build.sh writes this clone's bin/brain path into the bundle, so the app works wherever Brain is cloned.
let brainBin = (try? String(contentsOf: Bundle.main.url(forResource: "brain-path", withExtension: nil)!, encoding: .utf8))?
    .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
let url = URL(string: "http://127.0.0.1:\(ProcessInfo.processInfo.environment["BRAIN_PORT"] ?? "4747")/")!

// Runs at page start: mark the native shell (app/theme.css styles html.native) and default new installs to Mac glass.
let boot = """
document.documentElement.classList.add('native');
try { if (!localStorage.getItem('brain.theme')) localStorage.setItem('brain.theme', 'macglass/auto'); } catch (e) {}
"""

// The page runs under the hidden title bar, so the web view would swallow every click up there. This strip, the height
// of a normal title bar, sits on top: drag it to move the window, double-click to zoom (or whatever the user set in
// System Settings), like any Mac app. The page keeps its controls below it (theme.css: html.native .bar).
final class TitleStrip: NSView {
    override func mouseDown(with e: NSEvent) {
        if e.clickCount == 2 {
            let act = UserDefaults.standard.string(forKey: "AppleActionOnDoubleClick") ?? "Maximize"
            act == "Minimize" ? window?.performMiniaturize(nil) : act == "None" ? () : window?.performZoom(nil)
        } else {
            window?.performDrag(with: e)
        }
    }
}

final class App: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var web: WKWebView!

    func applicationDidFinishLaunching(_ n: Notification) {
        buildMenu()
        let config = WKWebViewConfiguration()
        config.userContentController.addUserScript(WKUserScript(source: boot, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        web = WKWebView(frame: .zero, configuration: config)
        web.setValue(false, forKey: "drawsBackground")  // transparent, so the blur below shows
        web.navigationDelegate = self
        web.uiDelegate = self
        web.autoresizingMask = [.width, .height]

        let blur = NSVisualEffectView()
        blur.material = .fullScreenUI  // follows light/dark; .hudWindow is always dark
        blur.blendingMode = .behindWindow
        blur.state = .active
        blur.autoresizingMask = [.width, .height]
        web.frame = blur.bounds
        blur.addSubview(web)

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 860),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
                          backing: .buffered, defer: false)
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.isOpaque = false
        window.backgroundColor = .clear
        window.isMovableByWindowBackground = false
        window.contentView = blur
        let strip = TitleStrip(frame: NSRect(x: 0, y: blur.bounds.height - 28, width: blur.bounds.width, height: 28))
        strip.autoresizingMask = [.width, .minYMargin]
        blur.addSubview(strip)
        window.center()
        window.setFrameAutosaveName("Brain")
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        startServerThenLoad()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }

    // Start the server if it isn't answering (bin/brain keeps it running after the app quits), then load.
    func startServerThenLoad() {
        DispatchQueue.global().async {
            if !self.up() {
                let p = Process()
                p.executableURL = URL(fileURLWithPath: "/bin/bash")
                p.arguments = ["-lc", "BRAIN_NO_BROWSER=1 '\(brainBin)'"]
                try? p.run()
                for _ in 0..<50 where !self.up() { usleep(100_000) }
            }
            DispatchQueue.main.async { self.web.load(URLRequest(url: url)) }
        }
    }

    func up() -> Bool {
        var ok = false
        let done = DispatchSemaphore(value: 0)
        var req = URLRequest(url: url); req.timeoutInterval = 0.5
        URLSession.shared.dataTask(with: req) { _, r, _ in ok = (r as? HTTPURLResponse) != nil; done.signal() }.resume()
        done.wait()
        return ok
    }

    // Links that leave Brain open in the default browser.
    func webView(_ w: WKWebView, decidePolicyFor a: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let u = a.request.url, a.navigationType == .linkActivated, u.host != url.host {
            NSWorkspace.shared.open(u); decisionHandler(.cancel); return
        }
        decisionHandler(.allow)
    }

    func webView(_ w: WKWebView, createWebViewWith c: WKWebViewConfiguration, for a: WKNavigationAction, windowFeatures f: WKWindowFeatures) -> WKWebView? {
        if let u = a.request.url { NSWorkspace.shared.open(u) }
        return nil
    }

    func webView(_ w: WKWebView, didFailProvisionalNavigation n: WKNavigation!, withError e: Error) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { w.load(URLRequest(url: url)) }  // server still starting
    }

    @objc func reload() { web.reload() }

    func buildMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem(); main.addItem(appItem)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Reload", action: #selector(reload), keyEquivalent: "r")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Hide Brain", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(withTitle: "Quit Brain", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        let editItem = NSMenuItem(); main.addItem(editItem)
        let edit = NSMenu(title: "Edit")
        for (t, s, k) in [("Undo", "undo:", "z"), ("Redo", "redo:", "Z"), ("Cut", "cut:", "x"), ("Copy", "copy:", "c"),
                          ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")] {
            edit.addItem(withTitle: t, action: Selector(s), keyEquivalent: k)
        }
        editItem.submenu = edit
        let winItem = NSMenuItem(); main.addItem(winItem)
        let win = NSMenu(title: "Window")
        win.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        win.addItem(withTitle: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        winItem.submenu = win
        NSApp.mainMenu = main
    }
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
