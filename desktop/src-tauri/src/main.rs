// Demel desktop: a tray icon that follows Demel's sip reminders over SSE and
// covers every monitor with Demel's reminder page while a sip is due.
// (Formerly the Drinky app; the schedule and the water log now live in Demel.)
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader};
use std::{fs, path::PathBuf, thread, time::Duration};
use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder, WindowEvent, Wry};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};

/// Demel address and this computer's device token (from /api/auth/device).
#[derive(Clone, Default)]
struct Conn {
    url: String,
    token: String,
}

impl Conn {
    fn ready(&self) -> bool {
        !self.url.is_empty() && !self.token.is_empty()
    }
    fn bearer(&self) -> String {
        format!("Bearer {}", self.token)
    }
    /// A Demel page that logs its window in with the device token. The page swaps
    /// the token for a cookie; a URL fragment is never sent to the server.
    fn page(&self, query: &str) -> Option<tauri::Url> {
        format!("{}/{query}#device={}", self.url, self.token).parse().ok()
    }
}

fn config_file(app: &AppHandle) -> PathBuf {
    app.path().app_config_dir().expect("config dir").join("connection.txt")
}

fn clean(url: &str) -> String {
    url.trim().trim_end_matches('/').to_string()
}

fn load(app: &AppHandle) -> Conn {
    let text = fs::read_to_string(config_file(app)).unwrap_or_default();
    let mut lines = text.lines();
    Conn {
        url: clean(lines.next().unwrap_or("")),
        token: lines.next().unwrap_or("").trim().to_string(),
    }
}

#[tauri::command]
fn get_server(app: AppHandle) -> String {
    load(&app).url
}

// Connect window: trade the Demel password for a device token once, keep the
// token (never the password), restart to connect.
#[tauri::command]
fn connect(app: AppHandle, url: String, password: String) -> Result<(), String> {
    let url = clean(&url);
    let body = serde_json::json!({ "password": password }).to_string();
    let res = ureq::post(&format!("{url}/api/auth/device"))
        .set("content-type", "application/json")
        .send_string(&body)
        .map_err(|e| match e {
            ureq::Error::Status(401, _) => "Wrong password.".to_string(),
            ureq::Error::Status(429, _) => "Too many attempts. Try again in 15 minutes.".to_string(),
            ureq::Error::Status(code, _) => format!("Demel answered with HTTP {code}. Is this the right address?"),
            e => format!("Can't reach Demel: {e}"),
        })?;
    let text = res.into_string().map_err(|e| e.to_string())?;
    let reply: serde_json::Value = serde_json::from_str(&text).map_err(|e| e.to_string())?;
    let token = reply["token"].as_str().ok_or("Demel did not return a device token.")?;
    let path = config_file(&app);
    fs::create_dir_all(path.parent().unwrap()).map_err(|e| e.to_string())?;
    fs::write(&path, format!("{url}\n{token}\n")).map_err(|e| e.to_string())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(&path, fs::Permissions::from_mode(0o600));
    }
    app.restart()
}

// Tray actions: Demel works out the day and the sip size itself.
fn post(conn: Conn, path: &'static str, body: Option<String>) {
    thread::spawn(move || {
        let req = ureq::post(&format!("{}{path}", conn.url)).set("Authorization", &conn.bearer());
        let _ = match body {
            Some(body) => req.set("content-type", "application/json").send_string(&body),
            None => req.call(),
        };
    });
}

// Seconds since the last keyboard/mouse input, from the OS.
#[cfg(windows)]
fn idle_secs() -> u64 {
    #[repr(C)]
    struct LastInputInfo {
        cb_size: u32,
        dw_time: u32,
    }
    #[link(name = "user32")]
    extern "system" {
        fn GetLastInputInfo(info: *mut LastInputInfo) -> i32;
    }
    #[link(name = "kernel32")]
    extern "system" {
        fn GetTickCount() -> u32;
    }
    let mut info = LastInputInfo { cb_size: 8, dw_time: 0 };
    unsafe {
        if GetLastInputInfo(&mut info) == 0 {
            return 0;
        }
        (GetTickCount().wrapping_sub(info.dw_time) / 1000) as u64
    }
}

#[cfg(target_os = "macos")]
fn idle_secs() -> u64 {
    #[link(name = "CoreGraphics", kind = "framework")]
    extern "C" {
        fn CGEventSourceSecondsSinceLastEventType(state: i32, event_type: u32) -> f64;
    }
    // combined session state, any input event
    unsafe { CGEventSourceSecondsSinceLastEventType(0, u32::MAX) as u64 }
}

#[cfg(not(any(windows, target_os = "macos")))]
fn idle_secs() -> u64 {
    // No idle API wired up on Linux, so never claim presence and phones keep
    // getting pushes; read X11/Wayland idle time if it matters.
    u64::MAX
}

// While you use this computer, tell Demel every 30 s; it then skips the phone
// push because the overlay here is enough.
fn report_presence(conn: Conn) {
    loop {
        if idle_secs() < 120 {
            let _ = ureq::post(&format!("{}/api/hydration/presence", conn.url))
                .set("Authorization", &conn.bearer())
                .call();
        }
        thread::sleep(Duration::from_secs(30));
    }
}

fn open_window(app: &AppHandle, label: &str, url: WebviewUrl, w: f64, h: f64) {
    if let Some(win) = app.get_webview_window(label) {
        let _ = win.show();
        let _ = win.set_focus();
        return;
    }
    let _ = WebviewWindowBuilder::new(app, label, url)
        .title("Demel")
        .inner_size(w, h)
        .build();
}

fn show_overlay(app: &AppHandle, conn: &Conn) {
    let Some(url) = conn.page("?overlay=1&desktop=1") else { return };
    for (i, monitor) in app.available_monitors().unwrap_or_default().iter().enumerate() {
        let label = format!("overlay{i}");
        // Reuse the overlay hidden after the last reminder (see hide_overlay).
        let win = match app.get_webview_window(&label) {
            Some(win) => win,
            None => {
                let Ok(win) =
                    WebviewWindowBuilder::new(app, &label, WebviewUrl::External(url.clone()))
                        .title("Demel")
                        .decorations(false)
                        .always_on_top(true)
                        .skip_taskbar(true)
                        .visible_on_all_workspaces(true)
                        .resizable(false)
                        .visible(false)
                        .build()
                else {
                    continue;
                };
                win
            }
        };
        let _ = win.set_position(*monitor.position());
        // Windows/Linux: borderless fullscreen on that monitor (a raw physical
        // set_size mis-scales the page at 150% DPI). macOS: plain cover, since
        // fullscreen there would open a separate Space.
        if cfg!(target_os = "macos") {
            let _ = win.set_size(*monitor.size());
        } else {
            let _ = win.set_fullscreen(true);
        }
        let _ = win.show();
        if i == 0 {
            let _ = win.set_focus();
        }
    }
}

// Hide, never close: utilities like Swift Quit send the app a Quit Apple
// Event as soon as its last window closes. A hidden window keeps the app
// alive (and re-shows instantly).
fn hide_overlay(app: &AppHandle) {
    for (label, win) in app.webview_windows() {
        if label.starts_with("overlay") {
            let _ = win.hide();
        }
    }
}

// Follow Demel's SSE stream forever; it pings every ~20 s, so a silent
// minute means a dead connection and we reconnect.
fn listen(app: AppHandle, conn: Conn, today: MenuItem<Wry>) {
    let agent = ureq::AgentBuilder::new()
        .timeout_read(Duration::from_secs(60))
        .build();
    let mut due = false;
    loop {
        let res = agent
            .get(&format!("{}/api/hydration/events", conn.url))
            .set("Authorization", &conn.bearer())
            .call();
        match res {
            Ok(res) => {
                for line in BufReader::new(res.into_reader()).lines() {
                    let Ok(line) = line else { break };
                    let Some(data) = line.strip_prefix("data: ") else { continue };
                    let Ok(st) = serde_json::from_str::<serde_json::Value>(data) else { continue };
                    let drank = st["total"].as_f64().unwrap_or(0.0) / 1000.0;
                    let goal = st["goal"].as_f64().unwrap_or(0.0) / 1000.0;
                    let _ = today.set_text(format!("Today: {drank:.2} / {goal:.1} L"));
                    let now = st["due"].as_bool().unwrap_or(false);
                    if now != due {
                        due = now;
                        if now {
                            show_overlay(&app, &conn);
                        } else {
                            hide_overlay(&app);
                        }
                    }
                }
                let _ = today.set_text("Offline, reconnecting…");
            }
            Err(ureq::Error::Status(401, _)) => {
                // Password changed or the device was logged out.
                let _ = today.set_text("Signed out: choose Connect…");
                hide_overlay(&app);
                due = false;
                thread::sleep(Duration::from_secs(60));
                continue;
            }
            Err(_) => {
                let _ = today.set_text("Offline, reconnecting…");
            }
        }
        thread::sleep(Duration::from_secs(5));
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, None))
        .invoke_handler(tauri::generate_handler![get_server, connect])
        // Same reason as hide_overlay: closing "Open Demel" or "Connect…" hides
        // the window, so the tray app never ends up with zero windows.
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .setup(|app| {
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);

            let handle = app.handle().clone();
            let conn = load(&handle);
            let autostart = app.autolaunch();
            if !conn.ready() {
                let _ = autostart.enable(); // first run: start at login by default
            }

            let none = None::<&str>;
            let today = MenuItem::with_id(app, "today", "Today: –", false, none)?;
            let login = CheckMenuItem::with_id(
                app,
                "login",
                "Start at login",
                true,
                autostart.is_enabled().unwrap_or(false),
                none,
            )?;
            let menu = Menu::with_items(
                app,
                &[
                    &today,
                    &PredefinedMenuItem::separator(app)?,
                    &MenuItem::with_id(app, "drink", "I took a sip", true, none)?,
                    &MenuItem::with_id(app, "glass", "+250 ml glass", true, none)?,
                    &MenuItem::with_id(app, "bottle", "+500 ml bottle", true, none)?,
                    &MenuItem::with_id(app, "remind", "Remind everywhere now", true, none)?,
                    &MenuItem::with_id(app, "open", "Open Demel", true, none)?,
                    &PredefinedMenuItem::separator(app)?,
                    &MenuItem::with_id(app, "connect", "Connect…", true, none)?,
                    &login,
                    &MenuItem::with_id(app, "quit", "Quit", true, none)?,
                ],
            )?;

            let login_item = login.clone();
            TrayIconBuilder::new()
                .icon(app.default_window_icon().expect("icon").clone())
                .tooltip("Demel")
                .menu(&menu)
                .show_menu_on_left_click(true)
                .on_menu_event(move |app, event| match event.id().as_ref() {
                    "drink" => post(load(app), "/api/hydration/drink", None),
                    "glass" => post(load(app), "/api/hydration/drink", Some(r#"{"ml":250}"#.into())),
                    "bottle" => post(load(app), "/api/hydration/drink", Some(r#"{"ml":500}"#.into())),
                    "remind" => post(load(app), "/api/hydration/remind", None),
                    "open" => {
                        if let Some(url) = load(app).page("") {
                            open_window(app, "main", WebviewUrl::External(url), 1100.0, 800.0);
                        }
                    }
                    "connect" => open_window(app, "settings", WebviewUrl::default(), 440.0, 520.0),
                    "login" => {
                        let auto = app.autolaunch();
                        let on = auto.is_enabled().unwrap_or(false);
                        let _ = if on { auto.disable() } else { auto.enable() };
                        let _ = login_item.set_checked(!on);
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;

            if conn.ready() {
                let presence = conn.clone();
                thread::spawn(move || report_presence(presence));
                thread::spawn(move || listen(handle, conn, today));
            } else {
                let _ = today.set_text("Not connected");
                open_window(&handle, "settings", WebviewUrl::default(), 440.0, 520.0);
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Demel")
        .run(|_, event| {
            // Live in the tray: closing the last window must not quit.
            if let RunEvent::ExitRequested { api, code: None, .. } = event {
                api.prevent_exit();
            }
        });
}
