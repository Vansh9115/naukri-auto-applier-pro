# Naukri Auto-Applier Pro — containerized.
#
# Why this looks more involved than a typical Python Dockerfile: the bot
# always launches a *visible* browser (see naukri_bot.py, headless=False —
# not configurable), specifically so Google's login doesn't flag it as a
# bot. A container has no display, so this image runs a virtual one (Xvfb)
# and exposes it over noVNC — a browser-based VNC viewer — so you can open
# a tab, see the actual Chrome window, and complete the one-time Google
# login by hand, exactly like you would on a real desktop.
FROM python:3.12-bookworm

WORKDIR /app

# Real Google Chrome — the code prefers channel="chrome" over bundled
# Chromium specifically for login reliability, so we install the genuine
# browser, not just Playwright's fallback.
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget gnupg ca-certificates \
    && wget -q -O /tmp/google-chrome.deb \
        https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y --no-install-recommends /tmp/google-chrome.deb \
    && rm /tmp/google-chrome.deb \
    && rm -rf /var/lib/apt/lists/*

# Virtual display + browser-based VNC viewer, so the container's browser
# window is something you can actually see and click in.
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb x11vnc novnc websockify supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pulls in whatever system libraries the installed Playwright version's
# browsers need (matches whatever version requirements.txt resolved to,
# so this never drifts out of sync with the pip package).
RUN playwright install --with-deps chromium

# updater.py is included even though its self-update logic only ever
# activates in the frozen .exe (it no-ops here) — web_app.py imports it
# unconditionally at startup, so leaving it out would crash the container.
COPY web_app.py naukri_bot.py tracker.py updater.py version.txt index.html config.example.json ./
COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
RUN chmod +x /entrypoint.sh

ENV DISPLAY=:99

EXPOSE 5000 6080

ENTRYPOINT ["/entrypoint.sh"]
