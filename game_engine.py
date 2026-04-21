import random
import time

# Grid dimensions
GRID_W = 40
GRID_H = 30
GAME_DURATION = 300  # seconds
INITIAL_HEALTH = 200
TICK_INTERVAL = 1 / 6  # 6 ticks per second

# Pie types: (health_delta)
PIE_TYPES = {
    "golden": 15,
    "green": 8,
    "rotten": -10,
}

# Obstacle types: (damage)
OBSTACLE_TYPES = {
    "rock": -20,
    "spike": -30,
}


class Snake:
    def __init__(self, player_id, username, start_body, start_direction):
        self.player_id = player_id
        self.username = username
        self.body = list(start_body)       # list of (x,y), head first
        self.direction = start_direction   # (dx, dy)
        self.next_direction = start_direction
        self.health = INITIAL_HEALTH
        self.grow_pending = 0

    @property
    def head(self):
        return self.body[0]

    def set_direction(self, dx, dy):
        # prevent 180 degree reversal
        if (dx, dy) != (-self.direction[0], -self.direction[1]):
            self.next_direction = (dx, dy)

    def move(self):
        self.direction = self.next_direction
        hx, hy = self.head
        dx, dy = self.direction
        new_head = (hx + dx, hy + dy)
        self.body.insert(0, new_head)

        if self.grow_pending > 0:
            self.grow_pending -= 1
        else:
            self.body.pop()

    def to_dict(self):
        return {
            "player_id": self.player_id,
            "username": self.username,
            "body": self.body,
            "direction": list(self.direction),
            "health": self.health,
        }


class GameEngine:
    def __init__(self, username1, username2):
        self.snake1 = Snake(
            player_id=1,
            username=username1,
            start_body=[(5, 15), (4, 15), (3, 15)],
            start_direction=(1, 0)
        )
        self.snake2 = Snake(
            player_id=2,
            username=username2,
            start_body=[(35, 15), (36, 15), (37, 15)],
            start_direction=(-1, 0)
        )

        self.pies = {}        # (x, y) -> type_id
        self.obstacles = {}   # (x, y) -> type_id

        self.start_time = time.time()
        self.game_over = False
        self.winner = None
        self.end_reason = ""
        self._tick_count = 0

        self._generate_obstacles()
        self._generate_pies()

    # ─────────────────────────────────────────
    # Generation
    # ─────────────────────────────────────────

    def _free_cell(self):
        occupied = (
            set(self.snake1.body) |
            set(self.snake2.body) |
            set(self.pies.keys()) |
            set(self.obstacles.keys())
        )
        while True:
            x = random.randint(1, GRID_W - 2)
            y = random.randint(1, GRID_H - 2)
            if (x, y) not in occupied:
                return (x, y)

    def _generate_obstacles(self):
        for _ in range(12):
            cell = self._free_cell()
            self.obstacles[cell] = random.choice(list(OBSTACLE_TYPES.keys()))

    def _generate_pies(self):
        while len(self.pies) < 8:
            cell = self._free_cell()
            self.pies[cell] = random.choice(list(PIE_TYPES.keys()))

    # ─────────────────────────────────────────
    # Input
    # ─────────────────────────────────────────

    def handle_input(self, player_id, dx, dy):
        if player_id == 1:
            self.snake1.set_direction(dx, dy)
        elif player_id == 2:
            self.snake2.set_direction(dx, dy)

    # ─────────────────────────────────────────
    # Tick
    # ─────────────────────────────────────────

    def tick(self):
        if self.game_over:
            return

        self._tick_count += 1

        # move both snakes
        self.snake1.move()
        self.snake2.move()

        # check collisions
        self._check_collisions()

        # check time limit
        self._check_time_limit()

        # respawn pies if any were collected
        self._generate_pies()

    # ─────────────────────────────────────────
    # Collisions
    # ─────────────────────────────────────────

    def _check_collisions(self):
        self._check_snake_collisions(self.snake1, self.snake2)
        self._check_snake_collisions(self.snake2, self.snake1)
        self._check_head_on_collision()
        self._check_deaths()

    def _check_snake_collisions(self, snake, other):
        hx, hy = snake.head

        # wall collision
        if hx < 0 or hx >= GRID_W or hy < 0 or hy >= GRID_H:
            snake.health -= 20
            # push head back inside grid
            snake.body[0] = (
                max(0, min(GRID_W - 1, hx)),
                max(0, min(GRID_H - 1, hy))
            )

        # obstacle collision
        if snake.head in self.obstacles:
            obs_type = self.obstacles[snake.head]
            snake.health += OBSTACLE_TYPES[obs_type]

        # own body collision
        if snake.head in snake.body[1:]:
            snake.health -= 15

        # other snake body collision → instant death
        if snake.head in other.body:
            snake.health = 0

        # pie collection
        if snake.head in self.pies:
            pie_type = self.pies.pop(snake.head)
            delta = PIE_TYPES[pie_type]
            snake.health = max(0, min(200, snake.health + delta))
            snake.grow_pending += 1

        # clamp health
        snake.health = max(0, snake.health)

    def _check_head_on_collision(self):
        if self.snake1.head == self.snake2.head:
            self.snake1.health -= 100
            self.snake2.health -= 100
            self.snake1.health = max(0, self.snake1.health)
            self.snake2.health = max(0, self.snake2.health)

    def _check_deaths(self):
        s1_dead = self.snake1.health <= 0
        s2_dead = self.snake2.health <= 0

        if s1_dead and s2_dead:
            self.game_over = True
            self.winner = "Draw"
            self.end_reason = "Both snakes died simultaneously"

        elif s1_dead:
            self.game_over = True
            self.winner = self.snake2.username
            self.end_reason = f"{self.snake1.username} ran out of health"

        elif s2_dead:
            self.game_over = True
            self.winner = self.snake1.username
            self.end_reason = f"{self.snake2.username} ran out of health"

    def _check_time_limit(self):
        if self.game_over:
            return
        elapsed = time.time() - self.start_time
        if elapsed >= GAME_DURATION:
            self.game_over = True
            if self.snake1.health > self.snake2.health:
                self.winner = self.snake1.username
            elif self.snake2.health > self.snake1.health:
                self.winner = self.snake2.username
            else:
                self.winner = "Draw"
            self.end_reason = "Time limit reached"

    # ─────────────────────────────────────────
    # State snapshot
    # ─────────────────────────────────────────

    def get_state(self):
        elapsed = time.time() - self.start_time
        return {
            "tick": self._tick_count,
            "time_left": max(0, GAME_DURATION - elapsed),
            "snake1": self.snake1.to_dict(),
            "snake2": self.snake2.to_dict(),
            "pies": {f"{x},{y}": t for (x, y), t in self.pies.items()},
            "obstacles": {f"{x},{y}": t for (x, y), t in self.obstacles.items()},
            "game_over": self.game_over,
            "winner": self.winner,
            "end_reason": self.end_reason,
        }
