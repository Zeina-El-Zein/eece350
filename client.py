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
GRID_W = 48   
GRID_H = 34   
PANEL_W   = 260
WIN_W     = GRID_W * CELL_SIZE + PANEL_W
WIN_H     = GRID_H * CELL_SIZE + 60
FPS       = 60
SCREEN_SETTINGS = "settings"

C_BG      = (8,   10,  18)
C_GRID1   = (18,  22,  35)
C_GRID2   = (12,  16,  26)
C_PANEL   = (15,  18,  32)
C_WHITE   = (240, 240, 240)
C_GRAY    = (130, 130, 150)
C_GREEN   = (50,  230, 100)
C_RED     = (230,  60,  60)
C_YELLOW  = (255, 220,   0)
C_CYAN    = (0,   220, 230)
C_ACCENT  = (120, 190, 255)
C_ORANGE  = (255, 150,   0)
C_PURPLE  = (180,  80, 230)

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
    "golden": (255, 220,   0),
    "green":  (60,  230,  80),
    "rotten": (140,  90,  30),
}

BOX_COLORS = {
    "common": (255, 215,   0),   # gold
    "rare":   (180,  80, 220),   # purple
    "cursed": (139,   0,   0),   # dark red
}

OOBSTACLE_COLORS = {
    "rock":  (140, 140, 150),
    "spike": (220,  70,  70),
}

SCREEN_CONNECT = "connect"
SCREEN_SETUP   = "setup"
SCREEN_LOBBY   = "lobby"
SCREEN_GAME    = "game"
SCREEN_RESULT  = "result"
SCREEN_INTRO   = "intro"

# Direction labels in order for key setup
DIRECTIONS = ["UP", "DOWN", "RIGHT", "LEFT"]
DIRECTION_VECTORS = {
    "UP":    (0, -1),
    "DOWN":  (0,  1),
    "LEFT":  (-1, 0),
    "RIGHT": (1,  0),
}


class PithonClient:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Πthon Arena")
        self.screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)
        self.clock  = pygame.time.Clock()

        self.font_title = pygame.font.SysFont("Consolas", 64, bold=True)
        self.font_big   = pygame.font.SysFont("Consolas", 42, bold=True)
        self.font_med   = pygame.font.SysFont("Consolas", 24, bold=True)
        self.font_small = pygame.font.SysFont("Consolas", 18)
        self.font_tiny  = pygame.font.SysFont("Consolas", 14)

        # Network
        self.sock = None
        self._lock = threading.Lock()
        self._buf  = b""

        # App state
        self.screen_name   = SCREEN_INTRO    # start here instead of SCREEN_CONNECT
        self.username = ""
        self.intro_start   = time.time()
        self.intro_done    = False
        
        # Connect screen
        self.connect_err  = ""
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
        self.settings_key_focus = None   # which direction is waiting for keypress
        
        # Lobby
        self.player_list       = []
        self.selected_index    = 0
        self.lobby_msg         = ""
        self.show_connection_info = False
        self.session_wins   = 0
        self.session_losses = 0
        self.pending_challenge = None
        self.chat_focused = False  
        self.player1_color = (60, 200, 120)
        self.player2_color = (80, 140, 255)
        # Game
        self.game_state = None
        self.countdown_active = False
        self.countdown_start  = 0
        self.COUNTDOWN_SECS   = 10
        self.game_info  = {}
        self.notifications     = []    # list of (text, ttl)
        self.double_damage_active = False
        self.double_damage_until  = 0.0
        # Result
        self.result_data = {}
        # Chat
        self.chat_open    = False
        self.chat_input   = ""
        self.chat_log     = []    # list of (from, message)
        self.chat_log_max = 6     # max messages shown on screen
        #spectator:
        self.spectator_result_time = 0
        self.is_spectator = False
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
            self.username      = msg.get("username", self.input_uname)
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
            self.countdown_active = not msg.get("skip_countdown", False)
            self.countdown_start  = time.time()
            p1 = msg.get("player1")
            p2 = msg.get("player2")
            c1 = msg.get("color1", [60, 200, 120])
            c2 = msg.get("color2", [80, 140, 255])
            self.player1_color = tuple(c1)
            self.player2_color = tuple(c2)
            
            if p1 == self.username:
                self.my_player_id = 1
                self.is_spectator = False
            elif p2 == self.username:
                self.my_player_id = 2                
                self.is_spectator = False
            else:
                self.my_player_id = None
                self.is_spectator = True
            # tell server our color
            self._send({
                "type": "PLAYER_COLOR",
                "color": list(self.snake_color)
            })
        
        elif t == "GAME_STATE":
            prev = self.game_state
            self.game_state = msg

            # detect collected boxes
            if prev:
                prev_boxes = set(prev.get("boxes", {}).keys())
                curr_boxes = set(msg.get("boxes", {}).keys())
                collected  = prev_boxes - curr_boxes
                for key in collected:
                    # find which box was there in prev state
                    box_data = prev.get("boxes", {}).get(key, {})
                    t2 = box_data.get("type_id", "common")
                    if t2 == "common":
                        self.notifications.append(["Common Box: +50 HP!", 180])
                    elif t2 == "rare":
                        self.notifications.append(["Rare Box: +50 HP + Double Damage 30s!", 240])
                    elif t2 == "cursed":
                        self.notifications.append(["Cursed Box: -50 HP!", 180])

            # rest of existing GAME_STATE handling...
            for uname, text in msg.get("notifications", []):
                if uname == self.username:
                    self.notifications.append([text, 180])
            my_snake_key = "snake1" if self.my_player_id == 1 else "snake2"
            my_data = msg.get(my_snake_key, {})
            self.double_damage_active = my_data.get("double_damage", False)
            if self.double_damage_active:
                self.double_damage_until = time.time() + my_data.get("double_damage_remaining", 30)
        
        elif t == "GAME_OVER":
            self.result_data = msg
            self.screen_name = SCREEN_RESULT
            if self.is_spectator:
                self.spectator_result_time = time.time()
            elif msg.get("winner") == self.username:
                self.session_wins += 1
            else:
                self.session_losses += 1

        elif t == "ERROR":
            self.lobby_msg = msg.get("message", "Error")

        elif t == "CHAT_MSG":
            from_user = msg.get("from", "?")
            message   = msg.get("message", "")
            self.chat_log.append((from_user, message))
            if len(self.chat_log) > self.chat_log_max:
                self.chat_log.pop(0)

        elif t == "SPECTATE_OK":
            if not msg.get("game_in_progress", False):
                self.lobby_msg = "No game in progress to watch."
               
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
    def _ev_intro(self, ev):
        # any key skips the intro
        if ev.type == pygame.KEYDOWN or ev.type == pygame.MOUSEBUTTONDOWN:
            self.screen_name = SCREEN_CONNECT
    def _draw_intro(self):
        W, H    = self.screen.get_size()
        cx      = W // 2
        cy      = H // 2
        elapsed = time.time() - self.intro_start

        if elapsed < 1.0:
            alpha = int(255 * (elapsed / 1.0))
        else:
            alpha = 255

        alpha = max(0, min(255, alpha))

        # title
        title_surf = self.font_title.render("Πthon Arena", True, (180, 80, 230))
        title_surf.set_alpha(alpha)
        self.screen.blit(title_surf,
            (cx - title_surf.get_width() // 2, int(H * 0.25)))

        # subtitle
        if elapsed > 1.0:
            sub_surf = self.font_med.render("Network Snake Battle", True, C_ACCENT)
            sub_surf.set_alpha(alpha)
            self.screen.blit(sub_surf,
                (cx - sub_surf.get_width() // 2, int(H * 0.42)))

        # press any key — blinks
        if elapsed > 1.1:
            blink = int(elapsed * 2) % 2 == 0
            if blink:
                skip_surf = self.font_small.render("press any key to continue", True, C_GRAY)
                skip_surf.set_alpha(alpha)
                self.screen.blit(skip_surf,
                    (cx - skip_surf.get_width() // 2, int(H * 0.58)))

        # snake crawling across bottom — loops
        loop_duration = 6.0
        loop_elapsed  = elapsed % loop_duration
        snake_x = int((loop_elapsed / loop_duration) * (W + 160)) - 80

        for i in range(6):
            bx  = snake_x - i * 22
            col = C_CYAN if i == 0 else tuple(max(0, c - 40) for c in C_CYAN)
            pygame.draw.rect(self.screen, col,
                (bx, int(H * 0.88), 20, 20), border_radius=4)
            if i == 0:
                pygame.draw.circle(self.screen, (255, 255, 255),
                    (bx + 5, int(H * 0.88) + 5), 2)
                pygame.draw.circle(self.screen, (255, 255, 255),
                    (bx + 15, int(H * 0.88) + 5), 2)
                pygame.draw.circle(self.screen, C_BG,
                    (bx + 5, int(H * 0.88) + 5), 1)
                pygame.draw.circle(self.screen, C_BG,
                    (bx + 15, int(H * 0.88) + 5), 1)
    
    def _handle_event(self, ev):
        if   self.screen_name == SCREEN_CONNECT: self._ev_connect(ev)
        elif self.screen_name == SCREEN_SETUP:   self._ev_setup(ev)
        elif self.screen_name == SCREEN_LOBBY:   self._ev_lobby(ev)
        elif self.screen_name == SCREEN_GAME:    self._ev_game(ev)
        elif self.screen_name == SCREEN_RESULT:  self._ev_result(ev)
        elif self.screen_name == SCREEN_INTRO: self._ev_intro(ev)
        elif self.screen_name == SCREEN_SETTINGS: self._ev_settings(ev)
    def _draw(self):
        self._draw_background()    # replaces self.screen.fill(C_BG)
        if   self.screen_name == SCREEN_INTRO:   self._draw_intro()
        elif self.screen_name == SCREEN_CONNECT: self._draw_connect()
        elif self.screen_name == SCREEN_SETUP:   self._draw_setup()
        elif self.screen_name == SCREEN_LOBBY:   self._draw_lobby()
        elif self.screen_name == SCREEN_GAME:    self._draw_game()
        elif self.screen_name == SCREEN_RESULT:  self._draw_result()
        elif self.screen_name == SCREEN_SETTINGS: self._draw_settings()
        pygame.display.flip()

    # ─────────────────────────────────────
    # Connect screen
    # ─────────────────────────────────────
    def _draw_background(self):
        W, H = self.screen.get_size()
        self.screen.fill((8, 10, 18))
        for x in range(0, W, 40):
            pygame.draw.line(self.screen, (15, 18, 30), (x, 0), (x, H), 1)
        for y in range(0, H, 40):
            pygame.draw.line(self.screen, (15, 18, 30), (0, y), (W, y), 1)
        for px, py in [(0, 0), (W, 0), (0, H), (W, H)]:
            pygame.draw.circle(self.screen, (30, 40, 70), (px, py), 80)
            pygame.draw.circle(self.screen, (20, 28, 55), (px, py), 50)
    def _ev_connect(self, ev):
        W, H = self.screen.get_size()
        cx   = W // 2
        box_w = int(W * 0.4)
        box_x = cx - box_w // 2
        box_h = 44
        fields = [
            ("host",     int(H * 0.38)),
            ("port",     int(H * 0.50)),
            ("username", int(H * 0.62)),
        ]

        # ── Mouse clicks first ──
        if ev.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()
            for key, y in fields:
                if box_x <= mx <= box_x + box_w and y - box_h // 2 <= my <= y + box_h // 2:
                    self.active_field = key
            return

        # ── Keyboard ──
        if ev.type != pygame.KEYDOWN:
            return

        if ev.key in (pygame.K_TAB, pygame.K_DOWN):
            keys = ["host", "port", "username"]
            i = keys.index(self.active_field)
            self.active_field = keys[(i + 1) % 3]
        elif ev.key == pygame.K_UP:
            keys = ["host", "port", "username"]
            i = keys.index(self.active_field)
            self.active_field = keys[(i - 1) % 3]
        elif ev.key == pygame.K_RETURN:
            if self.active_field == "username":
                if self.input_host and self.input_port and self.input_uname:
                    self.connect()
            else:
                keys = ["host", "port", "username"]
                i = keys.index(self.active_field)
                self.active_field = keys[(i + 1) % 3]
        elif ev.key == pygame.K_BACKSPACE:
            if   self.active_field == "host":     self.input_host  = self.input_host[:-1]
            elif self.active_field == "port":     self.input_port  = self.input_port[:-1]
            elif self.active_field == "username": self.input_uname = self.input_uname[:-1]
        else:
            ch = ev.unicode
            nav_keys = [pygame.K_UP, pygame.K_DOWN, pygame.K_TAB,
                        pygame.K_RETURN, pygame.K_BACKSPACE, pygame.K_ESCAPE]
            if ch and ch.isprintable() and ev.key not in nav_keys:
                if self.active_field == "host":
                    if ch.isdigit() or ch == ".":
                        self.input_host += ch
                elif self.active_field == "port":
                    if ch.isdigit():
                        self.input_port += ch
                elif self.active_field == "username":
                    if ch.isalnum() or ch == "_":
                        self.input_uname += ch            

    def _draw_connect(self):
        W, H = self.screen.get_size()
        cx   = W // 2
        cy   = H // 2

        self._text("Πthon Arena", self.font_title, (180, 80, 230), cx, int(H * 0.12), center=True)
        self._text("Network Snake Battle", self.font_small, C_ACCENT, cx, int(H * 0.24), center=True)

        box_w = int(W * 0.4)
        box_h = 44
        box_x = cx - box_w // 2

        fields = [
            ("Server IP", self.input_host,  "host",     int(H * 0.38)),
            ("Port",      self.input_port,  "port",     int(H * 0.50)),
            ("Username",  self.input_uname, "username", int(H * 0.62)),
        ]
        for label, val, key, y in fields:
            active = self.active_field == key
            color  = C_ACCENT if active else C_GRAY
            pygame.draw.rect(self.screen, (15, 18, 35),
                (box_x, y - box_h // 2, box_w, box_h), border_radius=6)
            pygame.draw.rect(self.screen, color,
                (box_x, y - box_h // 2, box_w, box_h), 2, border_radius=6)
            self._text(f"{label}:", self.font_small, C_GRAY,
                box_x + 15, y - 8)
            cursor = "|" if active else ""
            self._text(f"{val}{cursor}", self.font_med, color,
                box_x + box_w // 2 + 20, y - 10)

        if self.connect_err:
            self._text(self.connect_err, self.font_small, C_RED,
                cx, int(H * 0.74), center=True)

        self._text("UP/DOWN to switch  •  ENTER to next  •  ENTER on username to connect",
            self.font_small, C_GRAY, cx, int(H * 0.88), center=True)
    # ─────────────────────────────────────
    # Setup screen
    # ─────────────────────────────────────

    def _ev_setup(self, ev):
        W, H = self.screen.get_size()
        cx   = W // 2

        # ── Mouse clicks ──
        if ev.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()

            # back button
            if 40 <= mx <= 130 and 20 <= my <= 54:
                if self.setup_from_lobby:
                    self.screen_name = SCREEN_LOBBY
                else:
                    if self.sock:
                        try:
                            self.sock.close()
                        except:
                            pass
                        self.sock = None
                    self.connect_err = ""
                    self.screen_name = SCREEN_CONNECT
                return

            if self.setup_phase == "color":
                box_w   = max(60, int(W * 0.07))
                box_h   = max(40, int(H * 0.08))
                total_w = len(SNAKE_COLOR_OPTIONS) * (box_w + 10)
                start_x = cx - total_w // 2
                box_y   = int(H * 0.30)
                for i in range(len(SNAKE_COLOR_OPTIONS)):
                    bx = start_x + i * (box_w + 10)
                    if bx <= mx <= bx + box_w and box_y <= my <= box_y + box_h:
                        self.snake_color_index = i
                        self.snake_color       = SNAKE_COLOR_OPTIONS[i][1]
                        self.setup_phase       = "keys"
                        self.key_capture_index = 0
                        self.key_map           = {}
                        self.key_names         = {"UP": "---", "DOWN": "---",
                                                "RIGHT": "---", "LEFT": "---"}

            elif self.setup_phase == "keys":
                box_w   = int(W * 0.4)
                box_x   = cx - box_w // 2
                box_h   = max(44, int(H * 0.08))
                gap     = int(H * 0.12)
                start_y = int(H * 0.30)
                for i, direction in enumerate(DIRECTIONS):
                    ky = start_y + i * gap
                    if box_x <= mx <= box_x + box_w and ky <= my <= ky + box_h:
                        self.key_capture_index = i
            return

        # ── Keyboard ──
        if ev.type != pygame.KEYDOWN:
            return

        if self.setup_phase == "color":
            if ev.key in (pygame.K_LEFT, pygame.K_UP):
                self.snake_color_index = (self.snake_color_index - 1) % len(SNAKE_COLOR_OPTIONS)
                self.snake_color = SNAKE_COLOR_OPTIONS[self.snake_color_index][1]
            elif ev.key in (pygame.K_RIGHT, pygame.K_DOWN):
                self.snake_color_index = (self.snake_color_index + 1) % len(SNAKE_COLOR_OPTIONS)
                self.snake_color = SNAKE_COLOR_OPTIONS[self.snake_color_index][1]
            elif ev.key == pygame.K_RETURN:
                self.setup_phase       = "keys"
                self.key_capture_index = 0
                self.key_map           = {}
                self.key_names         = {"UP": "---", "DOWN": "---",
                                        "RIGHT": "---", "LEFT": "---"}
            elif ev.key == pygame.K_ESCAPE:
                if self.setup_from_lobby:
                    self.screen_name = SCREEN_LOBBY
                else:
                    if self.sock:
                        try:
                            self.sock.close()
                        except:
                            pass
                        self.sock = None
                    self.connect_err = ""
                    self.screen_name = SCREEN_CONNECT

        elif self.setup_phase == "keys":
            if ev.key == pygame.K_ESCAPE:
                self.setup_phase = "color"
                return

            blocked = [pygame.K_LSHIFT, pygame.K_RSHIFT,
                    pygame.K_LCTRL, pygame.K_RCTRL,
                    pygame.K_LALT,  pygame.K_RALT]
            if ev.key in blocked:
                return

            direction_label = DIRECTIONS[self.key_capture_index]

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
        W, H = self.screen.get_size()
        cx   = W // 2

        self._text("Snake Setup", self.font_big, (180, 80, 230), cx, 40, center=True)
        pygame.draw.line(self.screen, C_ACCENT, (40, 85), (W - 40, 85), 1)

        # back button
        pygame.draw.rect(self.screen, (20, 25, 50), (40, 20, 90, 34), border_radius=6)
        pygame.draw.rect(self.screen, C_GRAY, (40, 20, 90, 34), 1, border_radius=6)
        self._text("< Back", self.font_tiny, C_GRAY, 85, 30, center=True)

        if self.setup_phase == "color":
            self._text("Choose your snake color",
                self.font_med, C_WHITE, cx, int(H * 0.15), center=True)
            self._text("LEFT / RIGHT to cycle   ENTER to confirm   or click a color",
                self.font_tiny, C_GRAY, cx, int(H * 0.22), center=True)

            box_w   = max(60, int(W * 0.07))
            box_h   = max(40, int(H * 0.08))
            cols    = len(SNAKE_COLOR_OPTIONS)
            total_w = cols * (box_w + 10)
            start_x = cx - total_w // 2
            box_y   = int(H * 0.30)

            for i, (name, color) in enumerate(SNAKE_COLOR_OPTIONS):
                bx  = start_x + i * (box_w + 10)
                sel = i == self.snake_color_index
                pygame.draw.rect(self.screen, color,
                    (bx, box_y, box_w, box_h), border_radius=8)
                pygame.draw.rect(self.screen, C_WHITE if sel else C_GRAY,
                    (bx, box_y, box_w, box_h), 3 if sel else 1, border_radius=8)
                self._text(name, self.font_tiny, C_WHITE,
                    bx + box_w // 2, box_y + box_h + 8, center=True)

            # preview
            prev_y = int(H * 0.55)
            self._text("Preview:", self.font_small, C_GRAY, cx, prev_y, center=True)
            for i in range(5):
                col = self.snake_color if i == 0 else tuple(max(0, c - 40) for c in self.snake_color)
                pygame.draw.rect(self.screen, col,
                    (cx - 55 + i * 24, prev_y + 30, 22, 22), border_radius=4)
                if i == 0:
                    pygame.draw.circle(self.screen, (255, 255, 255),
                        (cx - 50, prev_y + 36), 2)
                    pygame.draw.circle(self.screen, (255, 255, 255),
                        (cx - 38, prev_y + 36), 2)

            self._text("ESC to go back", self.font_tiny, C_GRAY,
                cx, int(H * 0.85), center=True)

        elif self.setup_phase == "keys":
            self._text("Set your movement keys",
                self.font_med, C_WHITE, cx, int(H * 0.15), center=True)
            self._text("Press any key for each direction   ESC to go back to color",
                self.font_tiny, C_GRAY, cx, int(H * 0.22), center=True)

            box_w  = int(W * 0.4)
            box_h  = max(44, int(H * 0.08))
            box_x  = cx - box_w // 2
            gap    = int(H * 0.12)
            start_y = int(H * 0.30)

            for i, direction in enumerate(DIRECTIONS):
                ky      = start_y + i * gap
                done    = i < self.key_capture_index
                active  = i == self.key_capture_index
                col     = C_ACCENT if active else C_GRAY

                label = self.key_names.get(direction, "?") if done else \
                        "Press key..." if active else "---"

                pygame.draw.rect(self.screen, (15, 18, 35),
                    (box_x, ky, box_w, box_h), border_radius=6)
                pygame.draw.rect(self.screen, C_ACCENT if active else C_GRAY,
                    (box_x, ky, box_w, box_h), 2 if active else 1, border_radius=6)
                self._text(f"{direction}:", self.font_med, col,
                    box_x + 20, ky + box_h // 2 - 10)
                self._text(label, self.font_med, col,
                    box_x + box_w // 2 + 20, ky + box_h // 2 - 10)
    # ─────────────────────────────────────
    # Lobby screen
    # ─────────────────────────────────────
    def _ev_lobby(self, ev):
        W, H  = self.screen.get_size()
        pad   = 30
        left_w = int(W * 0.48)

        # chat focused — intercept all keys
        if self.chat_focused:
            if ev.type != pygame.KEYDOWN:
                return
            if ev.key == pygame.K_RETURN:
                if self.chat_input.strip():
                    self._send({"type": "CHAT", "message": self.chat_input.strip()})
                    self.chat_log.append((self.username, self.chat_input.strip()))
                    if len(self.chat_log) > self.chat_log_max:
                        self.chat_log.pop(0)
                self.chat_input   = ""
                self.chat_focused = False
            elif ev.key == pygame.K_ESCAPE:
                self.chat_input   = ""
                self.chat_focused = False
            elif ev.key == pygame.K_BACKSPACE:
                self.chat_input = self.chat_input[:-1]
            else:
                if ev.unicode and ev.unicode.isprintable():
                    self.chat_input += ev.unicode
            return

        others = self._other_players()

        if ev.type == pygame.KEYDOWN:
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
            elif ev.key == pygame.K_ESCAPE:
                self.show_connection_info = False
                self.chat_focused = False

        if ev.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()
            cx     = W // 2

            # click player row to select
            for i, name in enumerate(others):
                y = 165 + i * 46
                if pad + 10 <= mx <= pad + left_w - 10 and y - 2 <= my <= y + 38:
                    if self.selected_index == i:
                        # second click on already selected = challenge
                        self._send({"type": "CHALLENGE", "target": name, "color": list(self.snake_color)})
                        self.lobby_msg = f"Challenge sent to {name}..."
                    else:
                        # first click = select
                        self.selected_index = i
                # challenge badge click
                challenge_x = pad + left_w - 130
                if challenge_x <= mx <= challenge_x + 110 and y + 6 <= my <= y + 30:
                    self._send({"type": "CHALLENGE", "target": name, "color": list(self.snake_color)})
                    self.lobby_msg = f"Challenge sent to {name}..."

            # settings button
            if W - 120 <= mx <= W - 20 and 20 <= my <= 56:
                self.settings_key_focus = None
                self.screen_name = SCREEN_SETTINGS

            # share button
            if pad <= mx <= pad + 180 and 75 <= my <= 107:
                self.show_connection_info = not self.show_connection_info

            # chat input box click
            chat_y  = 115 + int(H * 0.45) + 15
            chat_h  = H - chat_y - pad
            input_y = chat_y + chat_h - 36
            if pad + 5 <= mx <= pad + left_w - 5 and input_y <= my <= input_y + 30:
                self.chat_focused = True
            else:
                self.chat_focused = False

            # accept/decline popup buttons
            if self.pending_challenge:
                cy = H // 2
                if cx - 130 <= mx <= cx - 20 and cy + 5 <= my <= cy + 41:
                    self._send({"type": "CHALLENGE_RESP", "accepted": True, "color": list(self.snake_color)})
                    self.pending_challenge = None
                if cx + 20 <= mx <= cx + 130 and cy + 5 <= my <= cy + 41:
                    self._send({"type": "CHALLENGE_RESP", "accepted": False})
                    self.pending_challenge = None
            
            # watch game button
            left_top_h = int(H * 0.45)
            watch_y    = 115 + left_top_h - 45
            game_going = any(
                isinstance(p, dict) and p.get("status") == "in_game"
                for p in self.player_list
            )
            if game_going:
                if pad + 10 <= mx <= pad + left_w - 10 and watch_y <= my <= watch_y + 34:
                    self._send({"type": "SPECTATE"})       
    
    def _ev_settings(self, ev):
        W, H = self.screen.get_size()
        cx   = W // 2

        if ev.type == pygame.KEYDOWN:
            # if a key box is focused, assign the key
            if self.settings_key_focus:
                blocked = [pygame.K_ESCAPE, pygame.K_LSHIFT, pygame.K_RSHIFT,
                        pygame.K_LCTRL, pygame.K_RCTRL, pygame.K_LALT, pygame.K_RALT]
                if ev.key == pygame.K_ESCAPE:
                    self.settings_key_focus = None
                    return
                if ev.key in blocked:
                    return
                # prevent duplicate keys
                vector = DIRECTION_VECTORS[self.settings_key_focus]
                self.key_map = {k: v for k, v in self.key_map.items() if v != vector}
                if ev.key in self.key_map:
                    return
                self.key_map[ev.key] = vector
                self.key_names[self.settings_key_focus] = pygame.key.name(ev.key).upper()
                self.settings_key_focus = None
            else:
                if ev.key == pygame.K_ESCAPE:
                    self.screen_name = SCREEN_LOBBY

        if ev.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()

            # back button
            if 40 <= mx <= 130 and 20 <= my <= 54:
                self.screen_name = SCREEN_LOBBY

            # save button
            save_x = cx - 80
            save_y = H - 70
            if save_x <= mx <= save_x + 160 and save_y <= my <= save_y + 40:
                self.screen_name = SCREEN_LOBBY

            # color boxes
            box_w   = max(50, int((W // 2 - 60) / len(SNAKE_COLOR_OPTIONS)) - 8)
            box_h   = max(40, int(H * 0.08))
            total_w = len(SNAKE_COLOR_OPTIONS) * (box_w + 8)
            start_x = W // 4 - total_w // 2
            box_y   = int(H * 0.25)
            for i in range(len(SNAKE_COLOR_OPTIONS)):
                bx = start_x + i * (box_w + 8)
                if bx <= mx <= bx + box_w and box_y <= my <= box_y + box_h:
                    self.snake_color_index = i
                    self.snake_color = SNAKE_COLOR_OPTIONS[i][1]

            # key boxes
            key_x   = W // 2 + 20
            key_w   = W - key_x - 40
            gap     = int(H * 0.12)
            start_y = int(H * 0.25)
            box_h2  = max(44, int(H * 0.08))
            for i, direction in enumerate(DIRECTIONS):
                ky = start_y + i * gap
                if key_x <= mx <= key_x + key_w and ky <= my <= ky + box_h2:
                    self.settings_key_focus = direction
    def _draw_settings(self):
        W, H = self.screen.get_size()
        cx   = W // 2

        self._text("Settings", self.font_big, (180, 80, 230), cx, 40, center=True)
        pygame.draw.line(self.screen, C_ACCENT, (40, 85), (W - 40, 85), 1)

        # back button
        pygame.draw.rect(self.screen, (20, 25, 50), (40, 20, 90, 34), border_radius=6)
        pygame.draw.rect(self.screen, C_GRAY, (40, 20, 90, 34), 1, border_radius=6)
        self._text("< Back", self.font_tiny, C_GRAY, 85, 30, center=True)

        # ── LEFT — Color picker ──
        left_cx = W // 4
        self._text("Snake Color", self.font_med, C_ACCENT, left_cx, 100, center=True)
        self._text("Click a color to select", self.font_tiny, C_GRAY, left_cx, 130, center=True)

        box_w   = 80
        box_h   = 50
        cols    = len(SNAKE_COLOR_OPTIONS)
        total_w = cols * (box_w + 8)
        start_x = left_cx - total_w // 2

        for i, (name, color) in enumerate(SNAKE_COLOR_OPTIONS):
            bx  = start_x + i * (box_w + 8)
            sel = i == self.snake_color_index
            pygame.draw.rect(self.screen, color, (bx, 220, box_w, box_h), border_radius=8)
            pygame.draw.rect(self.screen, C_WHITE if sel else C_GRAY,
                (bx, 220, box_w, box_h), 3 if sel else 1, border_radius=8)
            self._text(name, self.font_tiny, C_WHITE,
                bx + box_w // 2, 278, center=True)

        # preview
        self._text("Preview:", self.font_small, C_GRAY, left_cx, 310, center=True)
        for i in range(5):
            col = self.snake_color if i == 0 else tuple(max(0, c - 40) for c in self.snake_color)
            pygame.draw.rect(self.screen, col,
                (left_cx - 55 + i * 24, 335, 22, 22), border_radius=4)
            if i == 0:
                pygame.draw.circle(self.screen, (255, 255, 255), (left_cx - 50, 341), 2)
                pygame.draw.circle(self.screen, (255, 255, 255), (left_cx - 38, 341), 2)
                pygame.draw.circle(self.screen, C_BG, (left_cx - 50, 341), 1)
                pygame.draw.circle(self.screen, C_BG, (left_cx - 38, 341), 1)

        # divider
        pygame.draw.line(self.screen, C_ACCENT, (cx - 10, 100), (cx - 10, H - 80), 1)

        # ── RIGHT — Key assignment ──
        key_x    = cx + 40
        right_cx = cx + (W - cx) // 2
        self._text("Movement Keys", self.font_med, C_ACCENT, right_cx, 100, center=True)
        self._text("Click a box then press a key", self.font_tiny, C_GRAY, right_cx, 130, center=True)

        for i, direction in enumerate(DIRECTIONS):
            ky      = 220 + i * 70
            focused = self.settings_key_focus == direction
            assigned = self.key_names.get(direction, "---")
            col     = C_ACCENT if focused else C_GRAY

            pygame.draw.rect(self.screen, (15, 18, 35), (key_x, ky, 300, 50), border_radius=6)
            pygame.draw.rect(self.screen, C_ACCENT if focused else C_GRAY,
                (key_x, ky, 300, 50), 2 if focused else 1, border_radius=6)

            self._text(f"{direction}:", self.font_med, col, key_x + 15, ky + 12)
            label = "Press a key..." if focused else assigned
            self._text(label, self.font_med, C_ACCENT if focused else C_WHITE,
                key_x + 160, ky + 12)

        # save button
        save_x = cx - 80
        save_y = H - 70
        pygame.draw.rect(self.screen, (20, 60, 20), (save_x, save_y, 160, 40), border_radius=8)
        pygame.draw.rect(self.screen, C_GREEN, (save_x, save_y, 160, 40), 2, border_radius=8)
        self._text("SAVE", self.font_med, C_GREEN, cx, save_y + 10, center=True)
    
    def _other_players(self):
        result = []
        for p in self.player_list:
            if isinstance(p, dict):
                if p.get("username") != self.username:
                    result.append(p.get("username"))
            elif p != self.username:
                result.append(p)
        return result

    def _draw_lobby(self):
        W, H = self.screen.get_size()
        cx   = W // 2
        pad  = 30

        left_w  = int(W * 0.48)
        right_x = left_w + pad * 2
        right_w = W - right_x - pad

        # ── Title ──
        self._text("LOBBY", self.font_big, (180, 80, 230), cx, 20, center=True)
        pygame.draw.line(self.screen, C_ACCENT, (pad, 68), (W - pad, 68), 1)

        # ── Share with Friend button ──
        pygame.draw.rect(self.screen, (20, 40, 70),
            (pad, 75, 180, 32), border_radius=6)
        pygame.draw.rect(self.screen, C_ACCENT,
            (pad, 75, 180, 32), 1, border_radius=6)
        self._text("Share with Friend", self.font_tiny, C_ACCENT,
            pad + 90, 83, center=True)

        # ── Settings button ──
        pygame.draw.rect(self.screen, (20, 25, 50),
            (W - 120, 20, 100, 36), border_radius=6)
        pygame.draw.rect(self.screen, C_GRAY,
            (W - 120, 20, 100, 36), 1, border_radius=6)
        self._text("Settings", self.font_tiny, C_GRAY, W - 70, 30, center=True)

        # ── LEFT — Online Players ──
        left_top_h = int(H * 0.45)
        pygame.draw.rect(self.screen, (15, 18, 32),
            (pad, 115, left_w, left_top_h), border_radius=8)
        pygame.draw.rect(self.screen, C_ACCENT,
            (pad, 115, left_w, left_top_h), 1, border_radius=8)
        self._text("Online Players", self.font_med, C_ACCENT, pad + 20, 125)
        pygame.draw.line(self.screen, C_ACCENT,
            (pad + 10, 155), (pad + left_w - 10, 155), 1)

        others = self._other_players()
        if not others:
            self._text("Waiting for others to join...",
                self.font_small, C_GRAY, pad + 20, 170)
        else:
            for i, name in enumerate(others):
                y   = 165 + i * 46
                sel = i == self.selected_index
                row_col = (25, 30, 55) if sel else (18, 22, 38)
                pygame.draw.rect(self.screen, row_col,
                    (pad + 10, y, left_w - 20, 38), border_radius=6)
                if sel:
                    pygame.draw.rect(self.screen, C_ACCENT,
                        (pad + 10, y, left_w - 20, 38), 1, border_radius=6)
                pygame.draw.circle(self.screen, C_GREEN, (pad + 30, y + 19), 6)
                col = C_GREEN if sel else C_WHITE
                self._text(name, self.font_med, col, pad + 50, y + 8)
                badge_x = pad + left_w - 130
                pygame.draw.rect(self.screen, (25, 70, 25),
                    (badge_x, y + 6, 110, 24), border_radius=4)
                self._text("available", self.font_tiny, C_GREEN,
                    badge_x + 55, y + 11, center=True)

        # ── LEFT BOTTOM — Chat ──
        chat_y = 115 + left_top_h + 15
        chat_h = H - chat_y - pad
        pygame.draw.rect(self.screen, (12, 15, 28),
            (pad, chat_y, left_w, chat_h), border_radius=8)
        pygame.draw.rect(self.screen, C_ACCENT,
            (pad, chat_y, left_w, chat_h), 1, border_radius=8)
        self._text("Chat", self.font_med, C_ACCENT, pad + 20, chat_y + 10)
        pygame.draw.line(self.screen, C_ACCENT,
            (pad + 10, chat_y + 38), (pad + left_w - 10, chat_y + 38), 1)

        # chat messages
        log_y = chat_y + 48
        for from_user, message in self.chat_log[-6:]:
            col  = C_GREEN if from_user == self.username else C_ACCENT
            text = f"{from_user}: {message}"
            if len(text) > 52:
                text = text[:49] + "..."
            if log_y < chat_y + chat_h - 50:
                self._text(text, self.font_tiny, col, pad + 15, log_y)
                log_y += 20

        # chat input box
        input_y = chat_y + chat_h - 36
        border_col = C_ACCENT if self.chat_focused else C_GRAY
        pygame.draw.rect(self.screen, (18, 22, 38),
            (pad + 5, input_y, left_w - 10, 30), border_radius=6)
        pygame.draw.rect(self.screen, border_col,
            (pad + 5, input_y, left_w - 10, 30), 2, border_radius=6)
        cursor   = "|" if self.chat_focused else ""
        display  = self.chat_input if self.chat_input else "Click here to chat..."
        text_col = C_WHITE if self.chat_input else C_GRAY
        self._text(f"{display}{cursor}", self.font_small, text_col,
            pad + 15, input_y + 6)

        # ── RIGHT TOP — Your Profile ──
        profile_h = int(H * 0.28)
        pygame.draw.rect(self.screen, (15, 18, 32),
            (right_x, 115, right_w, profile_h), border_radius=8)
        pygame.draw.rect(self.screen, C_ACCENT,
            (right_x, 115, right_w, profile_h), 1, border_radius=8)
        self._text("Your Profile", self.font_med, C_ACCENT, right_x + 20, 125)
        pygame.draw.line(self.screen, C_ACCENT,
            (right_x + 10, 155), (right_x + right_w - 10, 155), 1)
        pygame.draw.circle(self.screen, self.snake_color,
            (right_x + 30, 178), 10)
        self._text(self.username, self.font_med, C_WHITE, right_x + 50, 168)
        self._text(
            f"UP:{self.key_names.get('UP','?')}  DN:{self.key_names.get('DOWN','?')}  "
            f"RT:{self.key_names.get('RIGHT','?')}  LT:{self.key_names.get('LEFT','?')}",
            self.font_tiny, C_GRAY, right_x + 20, 200)
        for i in range(5):
            col = self.snake_color if i == 0 else tuple(max(0, c - 40) for c in self.snake_color)
            pygame.draw.rect(self.screen, col,
                (right_x + 20 + i * 22, 225, 20, 20), border_radius=4)
            if i == 0:
                pygame.draw.circle(self.screen, (255, 255, 255), (right_x + 25, 230), 2)
                pygame.draw.circle(self.screen, (255, 255, 255), (right_x + 35, 230), 2)

        # ── RIGHT MIDDLE — Session Stats ──
        stats_y = 115 + profile_h + 15
        stats_h = int(H * 0.14)
        pygame.draw.rect(self.screen, (15, 18, 32),
            (right_x, stats_y, right_w, stats_h), border_radius=8)
        pygame.draw.rect(self.screen, C_ACCENT,
            (right_x, stats_y, right_w, stats_h), 1, border_radius=8)
        self._text("Session Stats", self.font_med, C_ACCENT, right_x + 20, stats_y + 10)
        pygame.draw.line(self.screen, C_ACCENT,
            (right_x + 10, stats_y + 38), (right_x + right_w - 10, stats_y + 38), 1)
        self._text(f"Wins:   {self.session_wins}",
            self.font_small, C_GREEN, right_x + 20, stats_y + 48)
        self._text(f"Losses: {self.session_losses}",
            self.font_small, C_RED, right_x + 20, stats_y + 75)

        # ── RIGHT BOTTOM — Game Info + Obstacles/Controls (two columns) ──
        bottom_y = stats_y + stats_h + 15
        bottom_h = H - bottom_y - pad
        mid_x    = right_x + right_w // 2

        pygame.draw.rect(self.screen, (15, 18, 32),
            (right_x, bottom_y, right_w, bottom_h), border_radius=8)
        pygame.draw.rect(self.screen, C_ACCENT,
            (right_x, bottom_y, right_w, bottom_h), 1, border_radius=8)

        # vertical divider
        pygame.draw.line(self.screen, C_ACCENT,
            (mid_x, bottom_y + 45), (mid_x, bottom_y + bottom_h - 10), 1)

        # left column — Game Info + Pies
        self._text("Game Info", self.font_med, C_ACCENT, right_x + 15, bottom_y + 10)
        pygame.draw.line(self.screen, C_ACCENT,
            (right_x + 10, bottom_y + 38), (mid_x - 10, bottom_y + 38), 1)

        left_items = [
            ("Time:  5 min",     C_GRAY),
            ("HP:    100",       C_GRAY),
            ("",                 C_GRAY),
            ("Pies:",            C_YELLOW),
            (" Golden  +15 HP",  (255, 220, 0)),
            (" Green    +8 HP",  (60, 230, 80)),
            (" Rotten  -10 HP",  (140, 90, 30)),
        ]
        iy = bottom_y + 48
        for text, col in left_items:
            if iy < bottom_y + bottom_h - 10:
                self._text(text, self.font_tiny, col, right_x + 10, iy)
                iy += 20

        # right column — Obstacles + Controls
        self._text("Obstacles", self.font_med, C_ACCENT, mid_x + 15, bottom_y + 10)
        pygame.draw.line(self.screen, C_ACCENT,
            (mid_x + 10, bottom_y + 38), (right_x + right_w - 10, bottom_y + 38), 1)

        right_items = [
            ("Rock    -20 HP",   (160, 160, 160)),
            ("Spike   -30 HP",   (220, 70, 70)),
            ("Body    -15 HP",   C_GRAY),
            ("Opp.  -50 HP",     C_RED),
            ("Opp.  -100 w/Rare",C_PURPLE),
            ("",                 C_GRAY),
            ("Controls:",        C_ACCENT),
            ("UP/DN  select",    C_WHITE),
            ("ENTER  challenge", C_WHITE),
            ("Y/N  accept/dec",  C_GREEN),
        ]
        iy = bottom_y + 48
        for text, col in right_items:
            if iy < bottom_y + bottom_h - 10:
                self._text(text, self.font_tiny, col, mid_x + 10, iy)
                iy += 20

        # ── Connection info popup ──
        if self.show_connection_info:
            popup_w = 320
            popup_x = cx - popup_w // 2
            pygame.draw.rect(self.screen, (15, 20, 40),
                (popup_x, 115, popup_w, 120), border_radius=8)
            pygame.draw.rect(self.screen, C_ACCENT,
                (popup_x, 115, popup_w, 120), 2, border_radius=8)
            self._text("Share with your friend:", self.font_tiny, C_GRAY,
                cx, 125, center=True)
            self._text(f"IP:    {self.input_host}", self.font_med, C_GREEN,
                cx, 148, center=True)
            self._text(f"Port:  {self.input_port}", self.font_med, C_GREEN,
                cx, 178, center=True)
            self._text("ESC to close", self.font_tiny, C_GRAY,
                cx, 210, center=True)

        # ── Pending challenge popup ──
        if self.pending_challenge:
            self._draw_popup(
                f"{self.pending_challenge} is challenging you!")

        # ── Status message ──
        if self.lobby_msg:
            self._text(self.lobby_msg, self.font_small, C_YELLOW,
                cx, H - 20, center=True)
            
        game_going = any(
            isinstance(p, dict) and p.get("status") == "in_game"
            for p in self.player_list
        )
        if game_going:
            watch_y = 115 + left_top_h - 45
            pygame.draw.rect(self.screen, (20, 40, 70),
                (pad + 10, watch_y, left_w - 20, 34), border_radius=6)
            pygame.draw.rect(self.screen, C_CYAN,
                (pad + 10, watch_y, left_w - 20, 34), 1, border_radius=6)
            self._text("Watch Game", self.font_small, C_CYAN,
                pad + left_w // 2, watch_y + 8, center=True)
    # ─────────────────────────────────────
    # Game screen
    # ─────────────────────────────────────

    def _ev_game(self, ev):
        W, H     = self.screen.get_size()
        TOP      = 60
        panel_h  = GRID_H * CELL_SIZE
        chat_top = TOP + panel_h - 200
        input_y  = chat_top + 158
        sx       = GRID_W * CELL_SIZE + 10
        panel_w  = W - GRID_W * CELL_SIZE

        # chat click
        if ev.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()
            if sx <= mx <= sx + panel_w - 10 and input_y <= my <= input_y + 30:
                self.chat_focused = True
            else:
                self.chat_focused = False
            return

        # chat typing
        if self.chat_focused:
            if ev.type != pygame.KEYDOWN:
                return
            if ev.key == pygame.K_RETURN:
                if self.chat_input.strip():
                    self._send({"type": "CHAT", "message": self.chat_input.strip()})
                    self.chat_log.append((self.username, self.chat_input.strip()))
                    if len(self.chat_log) > self.chat_log_max:
                        self.chat_log.pop(0)
                self.chat_input   = ""
                self.chat_focused = False
            elif ev.key == pygame.K_ESCAPE:
                self.chat_input   = ""
                self.chat_focused = False
            elif ev.key == pygame.K_BACKSPACE:
                self.chat_input = self.chat_input[:-1]
            else:
                if ev.unicode and ev.unicode.isprintable():
                    self.chat_input += ev.unicode
            return

        # block input during countdown or if spectator
        if self.countdown_active:
            return
        if self.is_spectator:
            return
        if ev.type != pygame.KEYDOWN:
            return
        if ev.key in self.key_map and self.my_player_id in (1, 2):
            dx, dy = self.key_map[ev.key]
            self._send({"type": "INPUT", "direction": [dx, dy]})
    
    def _draw_game(self):
        
        W, H = self.screen.get_size()
        TOP  = 60
        gs   = self.game_state

        # update countdown
        if self.countdown_active:
            elapsed = time.time() - self.countdown_start
            if elapsed >= self.COUNTDOWN_SECS:
                self.countdown_active = False

        # top bar
        pygame.draw.rect(self.screen, (15, 18, 35), (0, 0, W, TOP))
        pygame.draw.line(self.screen, C_ACCENT, (0, TOP - 1), (W, TOP - 1), 2)
        if gs:
            tl   = int(gs.get("time_left", 0))
            m, s = divmod(tl, 60)
            s1   = gs.get("snake1", {})
            s2   = gs.get("snake2", {})

            # determine which snake is mine and which is opponent
            if self.my_player_id == 1:
                my_snake  = s1
                opp_snake = s2
                my_col    = self.player1_color
                opp_col   = self.player2_color
            elif self.my_player_id == 2:
                my_snake  = s2
                opp_snake = s1
                my_col    = self.player2_color
                opp_col   = self.player1_color
            else:
                # spectator
                my_snake  = s1
                opp_snake = s2
                my_col    = self.player1_color
                opp_col   = self.player2_color

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
                # subtle grid line
                pygame.draw.rect(self.screen, (25, 30, 45),
                    (gx * CELL_SIZE, TOP + gy * CELL_SIZE, CELL_SIZE, CELL_SIZE), 1)
        # border around grid
        pygame.draw.rect(self.screen, C_ACCENT,
            (0, TOP, GRID_W * CELL_SIZE, GRID_H * CELL_SIZE), 2)

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
                ("Own body  -15 HP",  C_GRAY),
                ("Opponent  -50 HP",       C_RED),
                ("Opp. -100 w/Rare box",   C_PURPLE),
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

        # boxes
        for key, box in gs.get("boxes", {}).items():
            x, y    = map(int, key.split(","))
            t       = box.get("type_id", "common")
            col     = BOX_COLORS.get(t, C_WHITE)
            px      = x * CELL_SIZE + 2
            py      = TOP + y * CELL_SIZE + 2
            bsize   = CELL_SIZE - 4
            pygame.draw.rect(self.screen, col, (px, py, bsize, bsize), border_radius=3)
            # symbol inside box
            cx3 = x * CELL_SIZE + CELL_SIZE // 2
            cy3 = TOP + y * CELL_SIZE + CELL_SIZE // 2
            if t == "common":
                self._text("+", self.font_tiny, (20, 20, 20), cx3, cy3 - 7, center=True)
            elif t == "rare":
                self._text("*", self.font_tiny, (255, 255, 255), cx3, cy3 - 7, center=True)
            elif t == "cursed":
                self._text("x", self.font_tiny, (255, 200, 200), cx3, cy3 - 7, center=True)
        
        # snakes
        for snake_key, pid in [("snake1", 1), ("snake2", 2)]:
            sdata = gs.get(snake_key, {})
            body  = sdata.get("body", [])
            col = self.player1_color if pid == 1 else self.player2_color
            # darker shade for body
            dark_col = tuple(max(0, c - 60) for c in col)

            for i, (bx, by) in enumerate(body):
                draw_col = col if i == 0 else dark_col
                pygame.draw.rect(self.screen, draw_col,
                    (bx * CELL_SIZE + 1, TOP + by * CELL_SIZE + 1,
                    CELL_SIZE - 2, CELL_SIZE - 2), border_radius=4)
                # bright border on head
                if i == 0:
                    pygame.draw.rect(self.screen, col,
                        (bx * CELL_SIZE + 1, TOP + by * CELL_SIZE + 1,
                        CELL_SIZE - 2, CELL_SIZE - 2), 2, border_radius=4)
                    # eyes
                    pygame.draw.circle(self.screen, (255, 255, 255),
                        (bx * CELL_SIZE + 5, TOP + by * CELL_SIZE + 5), 2)
                    pygame.draw.circle(self.screen, (255, 255, 255),
                        (bx * CELL_SIZE + CELL_SIZE - 5,
                        TOP + by * CELL_SIZE + 5), 2)
                    pygame.draw.circle(self.screen, C_BG,
                        (bx * CELL_SIZE + 5, TOP + by * CELL_SIZE + 5), 1)
                    pygame.draw.circle(self.screen, C_BG,
                        (bx * CELL_SIZE + CELL_SIZE - 5,
                        TOP + by * CELL_SIZE + 5), 1)

        # notifications
        new_notifs = []
        ny = TOP + 20
        for notif in self.notifications:
            text, ttl = notif
            alpha = min(255, ttl * 4)
            col   = C_RED if "DOUBLE" in text else C_YELLOW
            self._text(text, self.font_small, col, GRID_W * CELL_SIZE // 2, ny, center=True)
            notif[1] -= 1
            if notif[1] > 0:
                new_notifs.append(notif)
            ny += 28
        self.notifications = new_notifs

        # double damage indicator for current player
        if self.double_damage_active:
            remaining = max(0, self.double_damage_until - time.time())
            self._text(f"DOUBLE DAMAGE: {int(remaining)}s",
                self.font_small, C_PURPLE,
                GRID_W * CELL_SIZE // 2, TOP + GRID_H * CELL_SIZE - 30,
                center=True)  
    
        self._draw_side_panel(TOP)
        if self.is_spectator:
            self._text("SPECTATING", self.font_med, C_CYAN,
                GRID_W * CELL_SIZE // 2, 35, center=True)
    
    def _draw_chat(self):
        W, H = self.screen.get_size()
        box_w = 460
        box_x = 30
        box_y = H - 200

        # chat log background
        pygame.draw.rect(self.screen, (12, 15, 28),
            (box_x, box_y, box_w, 130), border_radius=8)
        pygame.draw.rect(self.screen, C_ACCENT,
            (box_x, box_y, box_w, 130), 1, border_radius=8)

        # messages
        log_y = box_y + 10
        for from_user, message in self.chat_log[-5:]:
            col  = C_GREEN if from_user == self.username else C_ACCENT
            text = f"{from_user}: {message}"
            if len(text) > 52:
                text = text[:49] + "..."
            self._text(text, self.font_tiny, col, box_x + 10, log_y)
            log_y += 22

        # input box — always visible
        input_y = box_y + 140
        border_col = C_ACCENT if self.chat_focused else C_GRAY
        pygame.draw.rect(self.screen, (18, 22, 38),
            (box_x, input_y, box_w, 36), border_radius=6)
        pygame.draw.rect(self.screen, border_col,
            (box_x, input_y, box_w, 36), 2, border_radius=6)
        cursor = "|" if self.chat_focused else ""
        display = self.chat_input if self.chat_input else "Click here to chat..."
        text_col = C_WHITE if self.chat_input else C_GRAY
        self._text(f"{display}{cursor}", self.font_small, text_col,
            box_x + 10, input_y + 8)
    
    def _draw_side_panel(self, top):
        W, H    = self.screen.get_size()
        sx      = GRID_W * CELL_SIZE + 10
        panel_w = W - GRID_W * CELL_SIZE
        panel_h = GRID_H * CELL_SIZE

        pygame.draw.rect(self.screen, C_PANEL,
            (GRID_W * CELL_SIZE, top, panel_w, panel_h))
        pygame.draw.line(self.screen, C_ACCENT,
            (GRID_W * CELL_SIZE, top),
            (GRID_W * CELL_SIZE, top + panel_h), 2)

        # ── Two column layout ──
        col1_x = sx
        col2_x = sx + panel_w // 2
        col_w  = panel_w // 2 - 10

        # ── Left column — Controls + Pies ──
        self._text("CONTROLS", self.font_small, C_CYAN, col1_x, top + 10)
        pygame.draw.line(self.screen, C_ACCENT,
            (col1_x, top + 28), (col1_x + col_w, top + 28), 1)

        left_hints = [
            f"UP:  {self.key_names.get('UP','?')}",
            f"DN:  {self.key_names.get('DOWN','?')}",
            f"LT:  {self.key_names.get('LEFT','?')}",
            f"RT:  {self.key_names.get('RIGHT','?')}",
            "",
            "Pies:",
            " o Golden +15HP",
            " o Green   +8HP",
            " x Rotten -10HP",
            "",
            "Boxes:",
            " + Common +50HP",
            " * Rare   +50HP",
            "   +2x dmg 30s",
            " x Cursed -50HP",
        ]
        y = top + 35
        for hint in left_hints:
            if hint.startswith("Pies"):         col = C_YELLOW
            elif hint.startswith("Boxes"):      col = C_PURPLE
            elif hint.startswith(" o Golden"):  col = (255, 220, 0)
            elif hint.startswith(" o Green"):   col = (60, 230, 80)
            elif hint.startswith(" x Rotten"):  col = (140, 90, 30)
            elif hint.startswith(" + Common"):  col = (255, 215, 0)
            elif hint.startswith(" * Rare"):    col = (180, 80, 220)
            elif hint.startswith("   +2x"):     col = (180, 80, 220)
            elif hint.startswith(" x Cursed"):  col = (139, 0, 0)
            else:                               col = C_GRAY
            self._text(hint, self.font_tiny, col, col1_x, y)
            y += 15

        # ── Right column — Obstacles + Collisions ──
        self._text("HAZARDS", self.font_small, C_RED, col2_x, top + 10)
        pygame.draw.line(self.screen, C_ACCENT,
            (col2_x, top + 28), (col2_x + col_w, top + 28), 1)

        right_hints = [
            "Obstacles:",
            " # Rock  -20HP",
            " ^ Spike -30HP",
            "",
            "Collisions:",
            " Own body -15HP",
            " Opp.     -50HP",
            " Opp+Rare-100HP",
            "",
            "Walls wrap",
            "around the grid",
        ]
        y = top + 35
        for hint in right_hints:
            if hint.startswith("Obstacles"):    col = C_RED
            elif hint.startswith("Collisions"): col = C_ORANGE
            elif hint.startswith(" # Rock"):    col = (160, 160, 160)
            elif hint.startswith(" ^ Spike"):   col = (220, 70, 70)
            elif "Rare" in hint:                col = C_PURPLE
            elif hint.startswith("Walls"):      col = C_CYAN
            elif hint.startswith("around"):     col = C_CYAN
            else:                               col = C_GRAY
            self._text(hint, self.font_tiny, col, col2_x, y)
            y += 15

        # ── Health bars ──
        if self.game_state:
            health_y = top + panel_h - 260
            pygame.draw.line(self.screen, C_ACCENT,
                (sx, health_y - 8), (W - 10, health_y - 8), 1)
            self._text("HEALTH", self.font_small, C_ACCENT, sx, health_y)
            for snake_key, pid in [("snake1", 1), ("snake2", 2)]:
                sdata = self.game_state.get(snake_key, {})
                hp    = max(0, min(100, sdata.get("health", 0)))
                uname = sdata.get("username", f"P{pid}")
                col   = self.player1_color if pid == 1 else self.player2_color
                label = f"{uname} (you)" if pid == self.my_player_id else uname
                health_y += 22
                self._text(label, self.font_tiny, col, sx, health_y)
                health_y += 14
                pygame.draw.rect(self.screen, (40, 40, 60),
                    (sx, health_y, panel_w - 20, 10), border_radius=4)
                bar_col = col if hp > 30 else C_RED
                pygame.draw.rect(self.screen, bar_col,
                    (sx, health_y, int((panel_w - 20) * hp / 100), 10), border_radius=4)
                self._text(f"{hp}", self.font_tiny, col, sx + panel_w - 18, health_y)
                health_y += 16

        # ── Chat box ──
        chat_top = top + panel_h - 155
        pygame.draw.line(self.screen, C_ACCENT,
            (sx, chat_top - 6), (W - 10, chat_top - 6), 1)
        self._text("CHAT", self.font_small, C_ACCENT, sx, chat_top)
        pygame.draw.rect(self.screen, (12, 15, 28),
            (sx, chat_top + 20, panel_w - 10, 90), border_radius=6)
        pygame.draw.rect(self.screen, C_ACCENT,
            (sx, chat_top + 20, panel_w - 10, 90), 1, border_radius=6)

        log_y = chat_top + 28
        for from_user, message in self.chat_log[-4:]:
            col  = C_GREEN if from_user == self.username else C_ACCENT
            text = f"{from_user}: {message}"
            if len(text) > 30:
                text = text[:27] + "..."
            if log_y < chat_top + 106:
                self._text(text, self.font_tiny, col, sx + 5, log_y)
                log_y += 20

        input_y = chat_top + 116
        border_col = C_ACCENT if self.chat_focused else C_GRAY
        pygame.draw.rect(self.screen, (18, 22, 38),
            (sx, input_y, panel_w - 10, 28), border_radius=6)
        pygame.draw.rect(self.screen, border_col,
            (sx, input_y, panel_w - 10, 28), 2, border_radius=6)
        cursor  = "|" if self.chat_focused else ""
        display = self.chat_input if self.chat_input else "click to chat..."
        tcol    = C_WHITE if self.chat_input else C_GRAY
        self._text(f"{display}{cursor}", self.font_tiny, tcol, sx + 5, input_y + 6)

    # ─────────────────────────────────────
    # Result screen
    # ─────────────────────────────────────

    def _ev_result(self, ev):
        W, H  = self.screen.get_size()
        cx    = W // 2
        btn_y = int(H * 0.65)

        # spectator auto-returns to lobby
        if self.is_spectator:
            self.screen_name  = SCREEN_LOBBY
            self.game_state   = None
            self.my_player_id = None
            self.is_spectator = False
            return

        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_RETURN:
            self.screen_name  = SCREEN_LOBBY
            self.game_state   = None
            self.my_player_id = None

        if ev.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()
            if cx - 180 <= mx <= cx + 180 and btn_y <= my <= btn_y + 44:
                self.screen_name  = SCREEN_LOBBY
                self.game_state   = None
                self.my_player_id = None

    def _draw_result(self):
        W, H   = self.screen.get_size()
        cx     = W // 2

        # spectator auto-return after 5 seconds
        if self.is_spectator:
            elapsed = time.time() - self.spectator_result_time
            if elapsed > 5.0:
                self.screen_name  = SCREEN_LOBBY
                self.game_state   = None
                self.my_player_id = None
                self.is_spectator = False
                return

        winner = self.result_data.get("winner", "?")
        reason = self.result_data.get("end_reason", "")
        scores = self.result_data.get("scores", {})
        is_win = winner == self.username

        col   = C_GREEN if is_win else C_RED
        label = "YOU WIN!" if is_win else \
                ("DRAW" if winner == "Draw" else f"{winner} WINS")

        self._text(label, self.font_big, col, cx, int(H * 0.25), center=True)
        self._text(reason, self.font_small, C_GRAY, cx, int(H * 0.35), center=True)

        if self.is_spectator:
            elapsed = time.time() - self.spectator_result_time
            secs_left = max(0, int(5 - elapsed) + 1)
            self._text(f"Returning to lobby in {secs_left}...",
                self.font_small, C_GRAY, cx, int(H * 0.42), center=True)

        y = int(H * 0.45)
        for uname, hp in scores.items():
            self._text(f"{uname}: {hp} HP", self.font_med, C_WHITE, cx, y, center=True)
            y += 40

        if not self.is_spectator:
            btn_y = int(H * 0.65)
            pygame.draw.rect(self.screen, (20, 60, 20),
                (cx - 180, btn_y, 360, 44), border_radius=8)
            pygame.draw.rect(self.screen, C_GREEN,
                (cx - 180, btn_y, 360, 44), 2, border_radius=8)
            self._text("ENTER or click to return to lobby",
                self.font_small, C_GREEN, cx, btn_y + 12, center=True)
    
    # ─────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────

    def _text(self, text, font, color, x, y, center=False, right=False):
        surf = font.render(text, True, color)
        if center: x -= surf.get_width() // 2
        if right:  x -= surf.get_width()
        self.screen.blit(surf, (x, y))

    def _draw_popup(self, text):
        W, H  = self.screen.get_size()
        cx    = W // 2
        cy    = H // 2
        w, h  = 520, 110
        pygame.draw.rect(self.screen, (20, 25, 50),
            (cx - w // 2, cy - h // 2, w, h), border_radius=8)
        pygame.draw.rect(self.screen, C_YELLOW,
            (cx - w // 2, cy - h // 2, w, h), 2, border_radius=8)
        self._text(text, self.font_small, C_YELLOW, cx, cy - 25, center=True)

        # Accept button
        pygame.draw.rect(self.screen, (20, 60, 20),
            (cx - 130, cy + 5, 110, 36), border_radius=6)
        pygame.draw.rect(self.screen, C_GREEN,
            (cx - 130, cy + 5, 110, 36), 2, border_radius=6)
        self._text("Y  Accept", self.font_small, C_GREEN, cx - 75, cy + 14, center=True)

        # Decline button
        pygame.draw.rect(self.screen, (60, 20, 20),
            (cx + 20, cy + 5, 110, 36), border_radius=6)
        pygame.draw.rect(self.screen, C_RED,
            (cx + 20, cy + 5, 110, 36), 2, border_radius=6)
        self._text("N  Decline", self.font_small, C_RED, cx + 75, cy + 14, center=True)


if __name__ == "__main__":
    PithonClient().run()
