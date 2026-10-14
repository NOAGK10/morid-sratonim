// מוסיף כפתור "הורדה" לדפי סרטונים ביוטיוב.
// הלחיצה פותחת קישור morid://, שמפעיל את התוכנה מוריד הסרטונים במחשב.
(() => {
  const ID = "morid-download";
  const PROTOCOL = "morid://download";

  function videoUrl() {
    const u = new URL(location.href);
    const v = u.searchParams.get("v");
    if (u.pathname === "/watch" && v) return `https://www.youtube.com/watch?v=${v}`;
    const shorts = u.pathname.match(/^\/shorts\/([\w-]+)/);
    if (shorts) return `https://www.youtube.com/shorts/${shorts[1]}`;
    return null;
  }

  function send(fmt) {
    const url = videoUrl();
    if (!url) return;
    location.href = `${PROTOCOL}?fmt=${fmt}&url=${encodeURIComponent(url)}`;
  }

  function build() {
    const wrap = document.createElement("div");
    wrap.id = ID;
    wrap.dir = "rtl";

    const main = document.createElement("button");
    main.className = "morid-main";
    main.type = "button";
    main.innerHTML =
      '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">' +
      '<path fill="currentColor" d="M11 4h2v8.2l3.3-3.3 1.4 1.4L12 16l-5.7-5.7 1.4-1.4 3.3 3.3zM5 18h14v2H5z"/></svg>' +
      "<span>הורדה</span>";

    const menu = document.createElement("div");
    menu.className = "morid-menu";
    for (const [fmt, label] of [["mp4", "MP4 וידאו"], ["mp3", "MP3 שמע"]]) {
      const item = document.createElement("button");
      item.type = "button";
      item.textContent = label;
      item.addEventListener("click", (e) => {
        e.stopPropagation();
        wrap.classList.remove("open");
        send(fmt);
      });
      menu.append(item);
    }

    main.addEventListener("click", (e) => {
      e.stopPropagation();
      wrap.classList.toggle("open");
    });
    document.addEventListener("click", () => wrap.classList.remove("open"));

    wrap.append(main, menu);
    return wrap;
  }

  function place() {
    const existing = document.getElementById(ID);
    if (!videoUrl()) {
      existing?.remove();
      return;
    }
    // בדף צפייה רגיל: ליד כפתור ההרשמה לערוץ. אחרת (למשל Shorts): כפתור צף בפינה.
    const anchor = location.pathname === "/watch" && document.querySelector("ytd-watch-metadata #owner");
    if (anchor) {
      if (existing?.parentElement !== anchor) {
        existing?.remove();
        anchor.append(build());
      }
      document.getElementById(ID).classList.remove("floating");
    } else if (!existing) {
      const el = build();
      el.classList.add("floating");
      document.body.append(el);
    }
  }

  // יוטיוב מחליף דפים בלי לטעון מחדש, אז בודקים שוב בכל מעבר ובכל שנייה
  document.addEventListener("yt-navigate-finish", place);
  setInterval(place, 1000);
  place();
})();
