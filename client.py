import socket
import threading
import pygame
import sys
import struct
import json
import time 
from protocol import send_message, receive_message

SERVER_IP = "127.0.0.1"
SERVER_PORT = 5000

# ─────────────────────────────────────────
# Constants
# ─────────────────────────────────────────
CELL_SIZE = 20
GRID_W    = 40
GRID_H    = 30
PANEL_W   = 260
WIN_W     = GRID_W * CELL_SIZE + PANEL_W
WIN_H     = GRID_H * CELL_SIZE + 60
FPS       = 60

C_BG      = (10,  12,  20)
C_GRID1   = (20,  24,  38)
C_GRID2   = (14,  18,  28)
C_PANEL   = (18,  22,  36)
C_WHITE   = (230, 230, 230)
C_GRAY    = (120, 120, 140)
C_GREEN   = (80,  220, 100)
C_RED     = (220,  80,  80)
C_YELLOW  = (255, 210,   0)
C_ACCENT  = (100, 180, 255)

# Available snake colors for the setup screen
SNAKE_COLOR_OPTIONS = [
    ("Green",  (60,  200, 120)),
    ("Blue",   (80,  140, 255)),
    ("Red",    (220,  80,  80)),
    ("Purple", (180,  80, 220)),
    ("Orange", (255, 140,   0)),
    ("Cyan",   (0,   210, 210)),
]

PIE_COLORS = {
    "golden": (255, 215,   0),
    "green":  (100, 220,  80),
    "rotten": (120,  80,  30),
}

OBSTACLE_COLORS = {
    "rock":  (130, 130, 130),
    "spike": (190, 190, 190),
}

SCREEN_CONNECT = "connect"
SCREEN_SETUP   = "setup"
SCREEN_LOBBY   = "lobby"
SCREEN_GAME    = "game"
SCREEN_RESULT  = "result"

# Direction labels in order for key setup
DIRECTIONS = ["UP", "DOWN", "LEFT", "RIGHT"]
DIRECTION_VECTORS = {
    "UP":    (0, -1),
    "DOWN":  (0,  1),
    "LEFT":  (-1, 0),
    "RIGHT": (1,  0),
}


class PithonClient:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Pithon Arena")
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        self.clock  = pygame.time.Clock()

        self.font_big   = pygame.font.SysFont("Consolas", 32, bold=True)
        self.font_med   = pygame.font.SysFont("Consolas", 20, bold=True)
        self.font_small = pygame.font.SysFont("Consolas", 15)
        self.font_tiny  = pygame.font.SysFont("Consolas", 12)

        # Network
        self.sock = None
        self._lock = threading.Lock()
        self._buf  = b""

        # App state
        self.screen_name  = SCREEN_CONNECT
        self.username     = ""
        self.my_player_id = None
        self.connect_err  = ""

        # Connect screen
        self.input_host   = "127.0.0.1"
        self.input_port   = "5000"
        self.input_uname  = ""
        self.active_field = "host"

        # ── Setup screen state ──
        self.snake_color       = SNAKE_COLOR_OPTIONS[0][1]   # default green
        self.snake_color_index = 0
        self.key_map           = {                            # default keys
            pygame.K_UP:    (0, -1),
            pygame.K_DOWN:  (0,  1),
            pygame.K_LEFT:  (-1, 0),
            pygame.K_RIGHT: (1,  0),
        }
        # key_names stores display strings like "UP", "DOWN", "LEFT ARROW"
        self.key_names = {
            "UP":    "UP ARROW",
            "DOWN":  "DOWN ARROW",
            "LEFT":  "LEFT ARROW",
            "RIGHT": "RIGHT ARROW",
        }
        self.setup_phase       = "color"   # "color" or "keys"
        self.key_capture_index = 0         # which direction we're capturing (0-3)
        self.setup_from_lobby  = False     # True if opened from lobby settings

        # Lobby
        self.player_list       = []
        self.selected_index    = 0
        self.lobby_msg         = ""
        self.pending_challenge = None

        # Game
        self.game_state = None
        self.countdown_active = False
        self.countdown_start  = 0
        self.COUNTDOWN_SECS   = 10
        self.game_info  = {}

        # Result
        self.result_data = {}

    # ─────────────────────────────────────
    # Networking
    # ─────────────────────────────────────

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.input_host, int(self.input_port)))
            self.sock.setblocking(False)
            self._send({"type": "JOIN", "username": self.input_uname})
        except Exception as e:
            self.connect_err = str(e)
            self.sock = None

    def _send(self, msg):
        if not self.sock:
            return
        try:
            with self._lock:
                send_message(self.sock, msg)
        except OSError:
            pass

    def poll_network(self):
        if not self.sock:
            return
        try:
            data = self.sock.recv(65536)
            if data:
                self._buf += data
                self._process_buf()
        except BlockingIOError:
            pass
        except OSError:
            pass

    def _process_buf(self):
        while len(self._buf) >= 4:
            length = struct.unpack("!I", self._buf[:4])[0]
            if len(self._buf) < 4 + length:
                break
            raw      = self._buf[4:4 + length]
            self._buf = self._buf[4 + length:]
            msg      = json.loads(raw.decode("utf-8"))
            self._handle_msg(msg)

    def _handle_msg(self, msg):
        t = msg.get("type")

        if t in ("JOIN_OK", "USERNAME_OK"):
            self.username    = msg.get("username", self.input_uname)
            # go to setup screen on first connection
            self.setup_phase       = "color"
            self.key_capture_index = 0
            self.setup_from_lobby  = False
            self.screen_name       = SCREEN_SETUP

        elif t == "USERNAME_TAKEN":
            self.connect_err = "Username already taken."
            self.sock = None

        elif t == "JOIN_FAIL":
            self.connect_err = msg.get("message", "Join failed.")
            self.sock = None

        elif t == "LOBBY":
            self.player_list = msg.get("players", [])

        elif t == "CHALLENGE_IN":
            self.pending_challenge = msg.get("from", "?")

        elif t == "GAME_START":
            self.game_info        = msg
            self.game_state       = None
            self.screen_name      = SCREEN_GAME
            self.countdown_active = True
            self.countdown_start  = time.time()
            p1 = msg.get("player1")
            p2 = msg.get("player2")
            self.my_player_id = 1 if p1 == self.username else \
                                2 if p2 == self.username else None
        elif t == "GAME_STATE":
            self.game_state = msg

        elif t == "GAME_OVER":
            self.result_data = msg
            self.screen_name = SCREEN_RESULT

        elif t == "ERROR":
            self.lobby_msg = msg.get("message", "Error")

    # ─────────────────────────────────────
    # Main loop
    # ─────────────────────────────────────

    def run(self):
        while True:
            self.poll_network()
            events = pygame.event.get()
            for ev in events:
                if ev.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                self._handle_event(ev)
            self._draw()
            self.clock.tick(FPS)

    def _handle_event(self, ev):
        if   self.screen_name == SCREEN_CONNECT: self._ev_connect(ev)
        elif self.screen_name == SCREEN_SETUP:   self._ev_setup(ev)
        elif self.screen_name == SCREEN_LOBBY:   self._ev_lobby(ev)
        elif self.screen_name == SCREEN_GAME:    self._ev_game(ev)
        elif self.screen_name == SCREEN_RESULT:  self._ev_result(ev)

    def _draw(self):
        self.screen.fill(C_BG)
        if   self.screen_name == SCREEN_CONNECT: self._draw_connect()
        elif self.screen_name == SCREEN_SETUP:   self._draw_setup()
        elif self.screen_name == SCREEN_LOBBY:   self._draw_lobby()
        elif self.screen_name == SCREEN_GAME:    self._draw_game()
        elif self.screen_name == SCREEN_RESULT:  self._draw_result()
        pygame.display.flip()

    # ─────────────────────────────────────
    # Connect screen
    # ─────────────────────────────────────

    def _ev_connect(self, ev):
        if ev.type != pygame.KEYDOWN:
            return
        if ev.key == pygame.K_TAB:
            fields = ["host", "port", "username"]
            self.active_field = fields[(fields.index(self.active_field) + 1) % 3]
        elif ev.key == pygame.K_RETURN:
            if self.input_host and self.input_port and self.input_uname:
                self.connect()
        elif ev.key == pygame.K_BACKSPACE:
            if   self.active_field == "host":     self.input_host  = self.input_host[:-1]
            elif self.active_field == "port":     self.input_port  = self.input_port[:-1]
            elif self.active_field == "username": self.input_uname = self.input_uname[:-1]
        else:
            ch = ev.unicode
            if   self.active_field == "host":     self.input_host  += ch
            elif self.active_field == "port":     self.input_port  += ch
            elif self.active_field == "username": self.input_uname += ch

    def _draw_connect(self):
        cx = WIN_W // 2
        self._text("Pithon Arena", self.font_big, C_GREEN, cx, 80, center=True)
        self._text("Network Snake Battle", self.font_small, C_GRAY, cx, 120, center=True)

        fields = [
            ("Server IP", self.input_host,  "host",     220),
            ("Port",      self.input_port,  "port",     280),
            ("Username",  self.input_uname, "username", 340),
        ]
        for label, val, key, y in fields:
            active = self.active_field == key
            color  = C_ACCENT if active else C_GRAY
            pygame.draw.rect(self.screen, color,
                (cx - 160, y - 18, 320, 36), 2, border_radius=4)
            self._text(f"{label}: {val}{'|' if active else ''}",
                self.font_small, color, cx, y, center=True)

        if self.connect_err:
            self._text(self.connect_err, self.font_small, C_RED, cx, 410, center=True)
        self._text("TAB to switch  •  ENTER to connect",
            self.font_tiny, C_GRAY, cx, WIN_H - 30, center=True)

    # ─────────────────────────────────────
    # Setup screen
    # ─────────────────────────────────────

    def _ev_setup(self, ev):
        if ev.type != pygame.KEYDOWN:
            return

        if self.setup_phase == "color":
            if ev.key == pygame.K_LEFT:
                self.snake_color_index = (self.snake_color_index - 1) % len(SNAKE_COLOR_OPTIONS)
                self.snake_color = SNAKE_COLOR_OPTIONS[self.snake_color_index][1]
            elif ev.key == pygame.K_RIGHT:
                self.snake_color_index = (self.snake_color_index + 1) % len(SNAKE_COLOR_OPTIONS)
                self.snake_color = SNAKE_COLOR_OPTIONS[self.snake_color_index][1]
            elif ev.key == pygame.K_RETURN:
                self.setup_phase       = "keys"
                self.key_capture_index = 0
                self.key_map           = {}    # clear all defaults so nothing is blocked
                self.key_names         = {"UP": "---", "DOWN": "---", "LEFT": "---", "RIGHT": "---"}
        elif self.setup_phase == "keys":
            direction_label = DIRECTIONS[self.key_capture_index]

            blocked = [pygame.K_ESCAPE, pygame.K_LSHIFT, pygame.K_RSHIFT,
                    pygame.K_LCTRL, pygame.K_RCTRL, pygame.K_LALT, pygame.K_RALT]
            if ev.key in blocked:
                return

            if ev.key in list(self.key_map.keys()):
                return

            vector = DIRECTION_VECTORS[direction_label]
            self.key_map = {k: v for k, v in self.key_map.items() if v != vector}
            self.key_map[ev.key] = vector
            self.key_names[direction_label] = pygame.key.name(ev.key).upper()

            self.key_capture_index += 1

            if self.key_capture_index >= len(DIRECTIONS):
                self.screen_name = SCREEN_LOBBY
                self.setup_phase = "color"

    def _draw_setup(self):
        cx = WIN_W // 2
        self._text("Snake Setup", self.font_big, C_GREEN, cx, 40, center=True)

        if self.setup_phase == "color":
            self._text("Choose your snake color",
                self.font_med, C_WHITE, cx, 100, center=True)
            self._text("LEFT / RIGHT to cycle   ENTER to confirm",
                self.font_tiny, C_GRAY, cx, 130, center=True)

            # Draw color options
            box_w, box_h = 100, 60
            total_w = len(SNAKE_COLOR_OPTIONS) * (box_w + 10)
            start_x = cx - total_w // 2

            for i, (name, color) in enumerate(SNAKE_COLOR_OPTIONS):
                x   = start_x + i * (box_w + 10)
                y   = 200
                sel = i == self.snake_color_index
                border_col = C_WHITE if sel else C_GRAY
                border_w   = 3 if sel else 1
                pygame.draw.rect(self.screen, color,
                    (x, y, box_w, box_h), border_radius=8)
                pygame.draw.rect(self.screen, border_col,
                    (x, y, box_w, box_h), border_w, border_radius=8)
                self._text(name, self.font_tiny, C_WHITE,
                    x + box_w // 2, y + box_h + 8, center=True)

            # Preview snake
            self._text("Preview:", self.font_small, C_GRAY, cx, 320, center=True)
            for i in range(5):
                pygame.draw.rect(self.screen, self.snake_color,
                    (cx - 50 + i * 22, 345, 20, 20), border_radius=4)
                if i == 0:
                    pygame.draw.circle(self.screen, C_BG,
                        (cx - 50 + 5, 350), 2)
                    pygame.draw.circle(self.screen, C_BG,
                        (cx - 50 + 15, 350), 2)

        elif self.setup_phase == "keys":
            self._text("Set your movement keys",
                self.font_med, C_WHITE, cx, 100, center=True)
            self._text("Press any key for each direction",
                self.font_tiny, C_GRAY, cx, 130, center=True)

            for i, direction in enumerate(DIRECTIONS):
                y     = 200 + i * 60
                done  = i < self.key_capture_index
                active = i == self.key_capture_index
                col   = C_GREEN if done else C_YELLOW if active else C_GRAY

                label = self.key_names.get(direction, "?") if done else \
                        "Press a key..." if active else "---"

                pygame.draw.rect(self.screen, (25, 30, 48),
                    (cx - 180, y - 5, 360, 44), border_radius=6)
                if active:
                    pygame.draw.rect(self.screen, C_YELLOW,
                        (cx - 180, y - 5, 360, 44), 2, border_radius=6)

                self._text(f"{direction}:", self.font_med, col, cx - 160, y)
                self._text(label, self.font_med, col, cx + 20, y)

    # ─────────────────────────────────────
    # Lobby screen
    # ─────────────────────────────────────

    def _ev_lobby(self, ev):
        if ev.type != pygame.KEYDOWN:
            return
        others = self._other_players()
        if ev.key == pygame.K_UP:
            self.selected_index = max(0, self.selected_index - 1)
        elif ev.key == pygame.K_DOWN:
            self.selected_index = min(len(others) - 1, self.selected_index + 1)
        elif ev.key == pygame.K_RETURN and others:
            target = others[self.selected_index]
            self._send({"type": "CHALLENGE", "target": target})
            self.lobby_msg = f"Challenge sent to {target}..."
        elif ev.key == pygame.K_y and self.pending_challenge:
            self._send({"type": "CHALLENGE_RESP", "accepted": True})
            self.pending_challenge = None
        elif ev.key == pygame.K_n and self.pending_challenge:
            self._send({"type": "CHALLENGE_RESP", "accepted": False})
            self.pending_challenge = None
        elif ev.key == pygame.K_s:
            # open settings
            self.setup_phase       = "color"
            self.key_capture_index = 0
            self.setup_from_lobby  = True
            self.screen_name       = SCREEN_SETUP

    def _other_players(self):
        return [p for p in self.player_list if p != self.username]

    def _draw_lobby(self):
        cx = WIN_W // 2
        self._text("LOBBY", self.font_big, C_GREEN, cx, 30, center=True)
        self._text(f"Logged in as: {self.username}",
            self.font_small, C_GRAY, cx, 70, center=True)

        # snake color preview dot next to username
        pygame.draw.circle(self.screen, self.snake_color,
            (cx + 130, 77), 8)

        others = self._other_players()
        self._text("Online Players:", self.font_med, C_ACCENT, 60, 110)

        if not others:
            self._text("Waiting for others to join...",
                self.font_small, C_GRAY, 60, 140)
        else:
            for i, name in enumerate(others):
                y   = 140 + i * 40
                sel = i == self.selected_index
                col = C_GREEN if sel else C_WHITE
                if sel:
                    pygame.draw.rect(self.screen, (30, 35, 55),
                        (50, y - 4, 340, 32), border_radius=4)
                self._text(name, self.font_med, col, 70, y)

        y = WIN_H - 180
        for hint in [
            "UP/DOWN  select player",
            "ENTER    challenge selected",
            "Y        accept challenge",
            "N        decline challenge",
            "S        settings (color & keys)",
        ]:
            self._text(hint, self.font_tiny, C_GRAY, 60, y)
            y += 22

        if self.pending_challenge:
            self._draw_popup(
                f"{self.pending_challenge} is challenging you!   Y=Accept   N=Decline")

        if self.lobby_msg:
            self._text(self.lobby_msg, self.font_small, C_YELLOW,
                cx, WIN_H - 30, center=True)

    # ─────────────────────────────────────
    # Game screen
    # ─────────────────────────────────────

    def _ev_game(self, ev):
        if self.countdown_active:
            return
        if ev.type != pygame.KEYDOWN:
            return
        if ev.key in self.key_map and self.my_player_id in (1, 2):
            dx, dy = self.key_map[ev.key]
            self._send({"type": "INPUT", "direction": [dx, dy]})
    def _draw_game(self):
        TOP = 60
        gs  = self.game_state

        # update countdown
        if self.countdown_active:
            elapsed = time.time() - self.countdown_start
            if elapsed >= self.COUNTDOWN_SECS:
                self.countdown_active = False

        # top bar
        pygame.draw.rect(self.screen, C_PANEL, (0, 0, WIN_W, TOP))
        if gs:
            tl   = int(gs.get("time_left", 0))
            m, s = divmod(tl, 60)
            s1   = gs.get("snake1", {})
            s2   = gs.get("snake2", {})

            # determine which snake is mine and which is opponent
            if self.my_player_id == 1:
                my_snake  = s1
                opp_snake = s2
                my_col    = self.snake_color
                opp_col   = (80, 140, 255)
            else:
                my_snake  = s2
                opp_snake = s1
                my_col    = self.snake_color
                opp_col   = (60, 200, 120)

            # opponent top left
            self._text(
                f"{opp_snake.get('username','OPP')}  HP:{opp_snake.get('health',0)}",
                self.font_med, opp_col, 10, 15)

            # timer center
            self._text(f"{m:02d}:{s:02d}", self.font_big, C_YELLOW,
                GRID_W * CELL_SIZE // 2, 10, center=True)

            # my HP top right
            self._text(
                f"{my_snake.get('username','ME')}  HP:{my_snake.get('health',0)}",
                self.font_med, my_col,
                GRID_W * CELL_SIZE - 10, 15, right=True)

        # grid
        for gx in range(GRID_W):
            for gy in range(GRID_H):
                col = C_GRID1 if (gx + gy) % 2 == 0 else C_GRID2
                pygame.draw.rect(self.screen, col,
                    (gx * CELL_SIZE, TOP + gy * CELL_SIZE, CELL_SIZE, CELL_SIZE))

        # countdown overlay
        if self.countdown_active:
            elapsed  = time.time() - self.countdown_start
            secs_left = max(0, int(self.COUNTDOWN_SECS - elapsed) + 1)

            # dim overlay
            overlay = pygame.Surface((GRID_W * CELL_SIZE, GRID_H * CELL_SIZE), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            self.screen.blit(overlay, (0, TOP))

            # big countdown number
            self._text(str(secs_left), self.font_big,
                C_YELLOW,
                GRID_W * CELL_SIZE // 2,
                TOP + GRID_H * CELL_SIZE // 2 - 80,
                center=True)

            self._text("GET READY!", self.font_med, C_WHITE,
                GRID_W * CELL_SIZE // 2,
                TOP + GRID_H * CELL_SIZE // 2 - 30,
                center=True)

            # hints during countdown
            hint_items = [
                ("PIES",      C_YELLOW),
                ("o Golden  +15 HP", (255, 215, 0)),
                ("o Green    +8 HP",  (100, 220, 80)),
                ("x Rotten  -10 HP",  (180, 120, 60)),
                ("", C_GRAY),
                ("OBSTACLES", C_RED),
                ("# Rock    -20 HP",  (160, 160, 160)),
                ("^ Spike   -30 HP",  (220, 100, 100)),
                ("", C_GRAY),
                ("COLLISIONS", (200, 200, 255)),
                ("Wall      -20 HP",  C_GRAY),
                ("Own body  -15 HP",  C_GRAY),
                ("Opponent  instant kill", C_RED),
            ]
            y = TOP + GRID_H * CELL_SIZE // 2 + 20
            for text, col in hint_items:
                self._text(text, self.font_tiny, col,
                    GRID_W * CELL_SIZE // 2, y, center=True)
                y += 20

            self._draw_side_panel(TOP)
            return

        if not gs:
            self._text("Waiting...", self.font_med, C_GRAY,
                GRID_W * CELL_SIZE // 2,
                TOP + GRID_H * CELL_SIZE // 2, center=True)
            self._draw_side_panel(TOP)
            return

        # obstacles
        for key, obs_type in gs.get("obstacles", {}).items():
            x, y = map(int, key.split(","))
            px = x * CELL_SIZE
            py = TOP + y * CELL_SIZE

            if obs_type == "rock":
                points = [
                    (px + 4,  py + 2),
                    (px + 14, py + 1),
                    (px + 18, py + 6),
                    (px + 17, py + 15),
                    (px + 11, py + 18),
                    (px + 3,  py + 17),
                    (px + 1,  py + 10),
                ]
                pygame.draw.polygon(self.screen, (130, 130, 130), points)
                pygame.draw.polygon(self.screen, (180, 180, 180), points, 1)

            elif obs_type == "spike":
                cx2 = px + CELL_SIZE // 2
                points = [
                    (cx2,     py + 2),
                    (px + 18, py + 17),
                    (px + 2,  py + 17),
                ]
                pygame.draw.polygon(self.screen, (200, 60, 60), points)
                pygame.draw.polygon(self.screen, (255, 120, 120), points, 1)

        # pies
        for key, pie_type in gs.get("pies", {}).items():
            x, y = map(int, key.split(","))
            cx2  = x * CELL_SIZE + CELL_SIZE // 2
            cy2  = TOP + y * CELL_SIZE + CELL_SIZE // 2
            col  = PIE_COLORS.get(pie_type, C_WHITE)

            if pie_type == "golden":
                pygame.draw.circle(self.screen, col, (cx2, cy2), CELL_SIZE // 2 - 2)
                pygame.draw.circle(self.screen, (255, 255, 180), (cx2, cy2), 4)

            elif pie_type == "green":
                points = [
                    (cx2,                cy2 - CELL_SIZE // 2 + 2),
                    (cx2 + CELL_SIZE // 2 - 2, cy2),
                    (cx2,                cy2 + CELL_SIZE // 2 - 2),
                    (cx2 - CELL_SIZE // 2 + 2, cy2),
                ]
                pygame.draw.polygon(self.screen, col, points)

            elif pie_type == "rotten":
                pygame.draw.circle(self.screen, col, (cx2, cy2), CELL_SIZE // 2 - 2)
                pygame.draw.line(self.screen, (60, 40, 10),
                    (cx2 - 4, cy2 - 4), (cx2 + 4, cy2 + 4), 2)
                pygame.draw.line(self.screen, (60, 40, 10),
                    (cx2 + 4, cy2 - 4), (cx2 - 4, cy2 + 4), 2)

        # snakes
        for snake_key, pid in [("snake1", 1), ("snake2", 2)]:
            sdata = gs.get(snake_key, {})
            body  = sdata.get("body", [])
            col   = self.snake_color if pid == self.my_player_id else \
                    (80, 140, 255) if self.my_player_id == 1 else (60, 200, 120)

            for i, (bx, by) in enumerate(body):
                pygame.draw.rect(self.screen, col,
                    (bx * CELL_SIZE + 1, TOP + by * CELL_SIZE + 1,
                    CELL_SIZE - 2, CELL_SIZE - 2), border_radius=4)
                if i == 0:
                    pygame.draw.circle(self.screen, C_BG,
                        (bx * CELL_SIZE + 5, TOP + by * CELL_SIZE + 5), 2)
                    pygame.draw.circle(self.screen, C_BG,
                        (bx * CELL_SIZE + CELL_SIZE - 5,
                        TOP + by * CELL_SIZE + 5), 2)

        self._draw_side_panel(TOP)
    def _draw_side_panel(self, top):
        sx = GRID_W * CELL_SIZE + 10
        pygame.draw.rect(self.screen, C_PANEL,
            (GRID_W * CELL_SIZE, top, PANEL_W, GRID_H * CELL_SIZE))

        self._text("CONTROLS", self.font_small, C_ACCENT, sx, top + 10)
        hints = [
            f"UP:    {self.key_names.get('UP',   '?')}",
            f"DOWN:  {self.key_names.get('DOWN', '?')}",
            f"LEFT:  {self.key_names.get('LEFT', '?')}",
            f"RIGHT: {self.key_names.get('RIGHT','?')}",
            "",
            "Pies:",
            "  o Golden  +15 HP",
            "  o Green    +8 HP",
            "  x Rotten  -10 HP",
            "",
            "Obstacles:",
            "  # Rock    -20 HP",
            "  ^ Spike   -30 HP",
            "",
            "Collisions:",
            "  Wall      -5 HP",
            "  Own body  -15 HP",
            "  Opponent  instant kill",
        ]
        y = top + 35
        for hint in hints:
            self._text(hint, self.font_tiny, C_GRAY, sx, y)
            y += 16

        if self.game_state:
            y = top + 380
            self._text("HEALTH", self.font_small, C_ACCENT, sx, y)
            for snake_key, pid in [("snake1", 1), ("snake2", 2)]:
                sdata = self.game_state.get(snake_key, {})
                hp    = max(0, min(100, sdata.get("health", 0)))
                uname = sdata.get("username", f"P{pid}")

                # my color vs opponent color
                if pid == self.my_player_id:
                    col = self.snake_color
                    label = f"{uname} (you)"
                else:
                    col = (80, 140, 255) if self.my_player_id == 1 else (60, 200, 120)
                    label = uname

                y += 25
                self._text(label, self.font_tiny, col, sx, y)
                y += 16
                # background bar
                pygame.draw.rect(self.screen, (40, 40, 60),
                    (sx, y, 220, 12), border_radius=4)
                # health bar — turns red below 30 HP
                bar_col = col if hp > 30 else C_RED
                pygame.draw.rect(self.screen, bar_col,
                    (sx, y, int(220 * hp / 100), 12), border_radius=4)
                # HP number next to bar
                self._text(f"{hp}", self.font_tiny, col, sx + 225, y)
                y += 20

    # ─────────────────────────────────────
    # Result screen
    # ─────────────────────────────────────

    def _ev_result(self, ev):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_RETURN:
            self.screen_name  = SCREEN_LOBBY
            self.game_state   = None
            self.my_player_id = None

    def _draw_result(self):
        cx     = WIN_W // 2
        winner = self.result_data.get("winner", "?")
        reason = self.result_data.get("end_reason", "")
        scores = self.result_data.get("scores", {})
        is_win = winner == self.username

        col   = C_GREEN if is_win else C_RED
        label = "YOU WIN!" if is_win else \
                ("DRAW" if winner == "Draw" else f"{winner} WINS")

        self._text(label, self.font_big, col, cx, WIN_H // 2 - 120, center=True)
        self._text(reason, self.font_small, C_GRAY, cx, WIN_H // 2 - 70, center=True)

        y = WIN_H // 2 - 20
        for uname, hp in scores.items():
            self._text(f"{uname}: {hp} HP",
                self.font_med, C_WHITE, cx, y, center=True)
            y += 36

        self._text("ENTER to return to lobby",
            self.font_small, C_GRAY, cx, WIN_H // 2 + 120, center=True)

    # ─────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────

    def _text(self, text, font, color, x, y, center=False, right=False):
        surf = font.render(text, True, color)
        if center: x -= surf.get_width() // 2
        if right:  x -= surf.get_width()
        self.screen.blit(surf, (x, y))

    def _draw_popup(self, text):
        cx, cy = WIN_W // 2, WIN_H // 2
        w, h   = 520, 60
        pygame.draw.rect(self.screen, (20, 25, 50),
            (cx - w // 2, cy - h // 2, w, h), border_radius=8)
        pygame.draw.rect(self.screen, C_YELLOW,
            (cx - w // 2, cy - h // 2, w, h), 2, border_radius=8)
        self._text(text, self.font_small, C_YELLOW, cx, cy - 8, center=True)


if __name__ == "__main__":
    PithonClient().run()