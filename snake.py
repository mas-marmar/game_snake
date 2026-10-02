import os
import sys
import math
import random
import pygame

# ---------- Инициализация ----------
pygame.init()

# ---------- Аудио (безопасная инициализация) ----------
AUDIO_OK = False
try:
    pygame.mixer.init()
    AUDIO_OK = True
except pygame.error as e:
    try:
        print(f"Аудио недоступно: {e}. Игра запустится без звука.")
    except Exception:
        pass


def log(msg):
    """Безопасный print — не падает в --windowed режиме."""
    try:
        print(msg)
    except Exception:
        pass


# ---------- Настройки окна ----------
CELL = 20
COLS, ROWS = 30, 30
WIDTH, HEIGHT = COLS * CELL, ROWS * CELL
FPS = 60

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("🐍 Змейка")
clock = pygame.time.Clock()

font_small = pygame.font.SysFont("Arial", 22, bold=True)
font_mid   = pygame.font.SysFont("Arial", 36, bold=True)
font_big   = pygame.font.SysFont("Arial", 52, bold=True)

# ---------- Цвета ----------
BG_COLOR      = (15, 15, 30)
GRID_COLOR    = (30, 30, 50)
GREEN_HEAD    = (74, 222, 128)
GREEN_TAIL    = (34, 122, 68)
RED           = (239, 68, 68)
WHITE         = (255, 255, 255)
BLACK         = (0, 0, 0)
GOLD_LIGHT    = (255, 247, 168)
GOLD_MID      = (255, 215, 0)
GOLD_DARK     = (184, 134, 11)
PORTAL_COLOR  = (74, 222, 128)

# ---------- Скорость игры ----------
START_SPEED_MS = 180
MIN_SPEED_MS   = 90
SPEED_STEP     = 2

# ---------- Настройки движущейся цели ----------
BONUS_LIFETIME = 7000
BONUS_COOLDOWN = 2500
BONUS_MOVE_MS  = 300

# ---------- Громкость ----------
MUSIC_VOLUME = 0.4
SFX_VOLUME   = 0.7


# ============================================================
#              ПУТИ К РЕСУРСАМ (работает и в .exe)
# ============================================================
def resource_path(rel):
    """Возвращает путь к ресурсу внутри .exe или в папке проекта."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


SOUNDS_DIR = resource_path("sounds")


def load_sound(filename):
    """Загружает звук, если файл существует. Иначе возвращает None."""
    if not AUDIO_OK:
        return None
    path = os.path.join(SOUNDS_DIR, filename)
    if os.path.exists(path):
        try:
            snd = pygame.mixer.Sound(path)
            snd.set_volume(SFX_VOLUME)
            return snd
        except pygame.error as e:
            log(f"Не удалось загрузить {filename}: {e}")
    return None


# Загружаем звуковые эффекты
sound_eat      = load_sound("eat.wav")
sound_bonus    = load_sound("bonus.wav")
sound_teleport = load_sound("teleport.wav")
sound_gameover = load_sound("gameover.wav")


def start_music():
    """Запускает фоновую музыку по кругу. Ищет .ogg, потом .mp3, потом .wav."""
    if not AUDIO_OK:
        return
    for ext in (".ogg", ".mp3", ".wav"):
        path = os.path.join(SOUNDS_DIR, "background" + ext)
        if os.path.exists(path):
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(MUSIC_VOLUME)
                pygame.mixer.music.play(-1)
            except pygame.error as e:
                log(f"Не удалось запустить музыку: {e}")
            return


def music_pause():
    if AUDIO_OK:
        pygame.mixer.music.pause()


def music_unpause():
    if AUDIO_OK:
        pygame.mixer.music.unpause()


def music_stop():
    if AUDIO_OK:
        pygame.mixer.music.stop()


# ============================================================
#                        КЛАСС ИГРЫ
# ============================================================
class SnakeGame:
    def __init__(self):
        self.reset()

    def reset(self):
        """Сброс в начальное состояние."""
        self.snake = [(COLS // 2, ROWS // 2)]
        self.direction = (1, 0)
        self.next_direction = (1, 0)
        self.score = 0
        self.bonus_score = 0
        self.speed = START_SPEED_MS
        self.last_move_time = 0

        self.game_over = False
        self.paused = False
        self.started = False

        # ⚠️ bonus ДО place_food, т.к. place_food его проверяет
        self.bonus = None
        self.bonus_next_spawn = pygame.time.get_ticks() + 3000

        # 🍎 Еда
        self.food = None
        self.place_food()

        # 🌀 Эффекты телепортации
        self.teleport_effects = []

    # --------------------------------------------------------
    #                  РАЗМЕЩЕНИЕ ОБЪЕКТОВ
    # --------------------------------------------------------
    def place_food(self):
        """Ставит яблоко в свободную клетку."""
        while True:
            pos = (random.randint(0, COLS - 1), random.randint(0, ROWS - 1))
            occupied = pos in self.snake
            if self.bonus and pos == (self.bonus['x'], self.bonus['y']):
                occupied = True
            if not occupied:
                self.food = pos
                return

    def spawn_bonus(self):
        """Создаёт движущуюся цель подальше от змейки."""
        x, y = 0, 0
        for _ in range(100):
            x = random.randint(0, COLS - 1)
            y = random.randint(0, ROWS - 1)
            if (x, y) in self.snake:
                continue
            if (x, y) == self.food:
                continue
            hx, hy = self.snake[0]
            if abs(x - hx) + abs(y - hy) < 5:
                continue
            break

        dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        d = random.choice(dirs)
        now = pygame.time.get_ticks()
        self.bonus = {
            'x': x, 'y': y,
            'prev_x': x, 'prev_y': y,   # для проверки пересечения траекторий
            'dir': d,
            'expires_at': now + BONUS_LIFETIME,
            'last_step': now,
        }

    def update_bonus(self, now):
        """Логика движущейся цели: спавн, движение, исчезновение."""
        if self.bonus is None:
            if now >= self.bonus_next_spawn:
                self.spawn_bonus()
            return

        if now >= self.bonus['expires_at']:
            self.bonus = None
            self.bonus_next_spawn = now + BONUS_COOLDOWN
            return

        if now - self.bonus['last_step'] >= BONUS_MOVE_MS:
            self.bonus['last_step'] = now
            dx, dy = self.bonus['dir']
            nx = self.bonus['x'] + dx
            ny = self.bonus['y'] + dy

            # 🌀 Телепортация через стены
            if nx < 0: nx = COLS - 1
            elif nx >= COLS: nx = 0
            if ny < 0: ny = ROWS - 1
            elif ny >= ROWS: ny = 0

            # 💡 Запоминаем старую позицию бонуса —
            #    она нужна для проверки «не прошёл ли бонус через голову»
            self.bonus['prev_x'] = self.bonus['x']
            self.bonus['prev_y'] = self.bonus['y']

            self.bonus['x'] = nx
            self.bonus['y'] = ny

    # --------------------------------------------------------
    #                    УПРАВЛЕНИЕ
    # --------------------------------------------------------
    def set_direction(self, x, y):
        if self.direction == (-x, -y):
            return
        self.next_direction = (x, y)
        if not self.started:
            self.started = True

    def play(self, sound):
        """Безопасно проигрывает звук (если он загружен)."""
        if sound:
            sound.play()

    # --------------------------------------------------------
    #          ПРОВЕРКА ПЕРЕСЕЧЕНИЯ ТРАЕКТОРИЙ
    # --------------------------------------------------------
    def _wrap_cell(self, cell):
        """Оборачивает координаты в границы поля (для проверки после телепорта)."""
        x, y = cell
        if x < 0: x = COLS - 1
        elif x >= COLS: x = 0
        if y < 0: y = ROWS - 1
        elif y >= ROWS: y = 0
        return (x, y)

    def _bonus_crossed_head(self, head_old_x, head_old_y, head_new):
        """
        Проверяет, пересеклись ли пути змейки и бонуса за последний кадр.
        Ловит три случая:
        1) Пути прошли через одну и ту же клетку (туннелирование).
        2) Змейка и бонус поменялись местами за кадр.
        3) Бонус «прилип» — оказался ровно на голове.
        """
        if not self.bonus:
            return False

        b = self.bonus
        prev = (b.get('prev_x', b['x']), b.get('prev_y', b['y']))
        cur  = (b['x'], b['y'])

        head_old = (head_old_x, head_old_y)
        snake_cells = {self._wrap_cell(head_old), head_new}
        bonus_cells = {prev, cur}

        # 1. Точное пересечение путей — обе прошли через одну клетку
        if snake_cells & bonus_cells:
            return True

        # 2. Обмен местами за кадр
        if head_old == cur and head_new == prev:
            return True

        # 3. Запасная проверка: бонус ровно под головой
        if head_new == cur:
            return True

        return False

    # --------------------------------------------------------
    #                   ИГРОВАЯ ЛОГИКА
    # --------------------------------------------------------
    def update(self, now):
        """Один шаг змейки."""
        if self.game_over or self.paused or not self.started:
            return

        self.direction = self.next_direction
        hx, hy = self.snake[0]
        dx, dy = self.direction
        head = (hx + dx, hy + dy)

        # 🌀 Телепортация через стены
        old_head = head
        if head[0] < 0: head = (COLS - 1, head[1])
        elif head[0] >= COLS: head = (0, head[1])
        if head[1] < 0: head = (head[0], ROWS - 1)
        elif head[1] >= ROWS: head = (head[0], 0)

        if old_head != head:
            # Эффекты вспышки на входе и выходе
            self.teleport_effects.append({
                'x': self.snake[0][0], 'y': self.snake[0][1], 'start': now
            })
            self.teleport_effects.append({
                'x': head[0], 'y': head[1], 'start': now
            })
            self.play(sound_teleport)

        # Что съедаем?
        will_eat_food = (head == self.food)
        will_eat_bonus = self.bonus and head == (self.bonus['x'], self.bonus['y'])

        # 💡 ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: не пролетел ли бонус сквозь голову
        #    за прошедший кадр (между двумя шагами змейки)
        if not will_eat_bonus and self.bonus:
            if self._bonus_crossed_head(hx, hy, head):
                will_eat_bonus = True

        # 💀 Проверка столкновения с хвостом
        body = self.snake if (will_eat_food or will_eat_bonus) else self.snake[:-1]
        if head in body:
            self.end_game()
            return

        self.snake.insert(0, head)

        if will_eat_food:
            self.score += 1
            self.place_food()
            self.speed = max(MIN_SPEED_MS, self.speed - SPEED_STEP)
            self.play(sound_eat)
        elif will_eat_bonus:
            self.score += 5
            self.bonus_score += 1
            self.bonus = None
            self.bonus_next_spawn = now + BONUS_COOLDOWN
            self.speed = max(MIN_SPEED_MS, self.speed - SPEED_STEP)
            self.play(sound_bonus)
        else:
            self.snake.pop()

    def end_game(self):
        self.game_over = True
        self.play(sound_gameover)

    # --------------------------------------------------------
    #                    ОТРИСОВКА
    # --------------------------------------------------------
    def draw(self, now):
        screen.fill(BG_COLOR)
        self._draw_grid()
        self._draw_portal_edges(now)
        self._draw_food()
        if self.bonus:
            self._draw_bonus(now)
        self._draw_snake()
        self._draw_teleport_effects(now)
        self._draw_hud()

        if self.paused and not self.game_over:
            self._draw_pause_overlay()
        if not self.started and not self.game_over:
            self._draw_start_overlay()
        if self.game_over:
            self._draw_game_over_overlay()

    def _draw_grid(self):
        for x in range(0, WIDTH, CELL):
            pygame.draw.line(screen, GRID_COLOR, (x, 0), (x, HEIGHT))
        for y in range(0, HEIGHT, CELL):
            pygame.draw.line(screen, GRID_COLOR, (0, y), (WIDTH, y))

    def _draw_portal_edges(self, now):
        pulse = 0.3 + 0.25 * math.sin(now / 300)
        alpha = int(255 * pulse)
        surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        color = (*PORTAL_COLOR, alpha)

        for x in range(COLS):
            cx = x * CELL + CELL // 2
            pygame.draw.rect(surf, color, (cx - 2, 0, 4, 3))
            pygame.draw.rect(surf, color, (cx - 2, HEIGHT - 3, 4, 3))
        for y in range(ROWS):
            cy = y * CELL + CELL // 2
            pygame.draw.rect(surf, color, (0, cy - 2, 3, 4))
            pygame.draw.rect(surf, color, (WIDTH - 3, cy - 2, 3, 4))

        screen.blit(surf, (0, 0))

    def _draw_food(self):
        fx, fy = self.food
        cx = fx * CELL + CELL // 2
        cy = fy * CELL + CELL // 2
        pygame.draw.circle(screen, RED, (cx, cy), CELL // 2 - 1)
        pygame.draw.circle(screen, (255, 200, 200), (cx - 3, cy - 3), 2)

    def _draw_bonus(self, now):
        b = self.bonus
        cx = b['x'] * CELL + CELL // 2
        cy = b['y'] * CELL + CELL // 2

        remaining = max(0, b['expires_at'] - now)
        life_ratio = remaining / BONUS_LIFETIME

        pulse = 1 + 0.15 * math.sin(now / 120)
        size = int((CELL // 2 - 1) * pulse)

        # Свечение
        glow_surf = pygame.Surface((CELL * 3, CELL * 3), pygame.SRCALPHA)
        for r in range(CELL, 0, -3):
            alpha = int(40 * (r / CELL))
            pygame.draw.circle(glow_surf, (255, 215, 0, alpha),
                               (CELL * 3 // 2, CELL * 3 // 2), r)
        screen.blit(glow_surf, (cx - CELL * 3 // 2, cy - CELL * 3 // 2))

        # Ромбик
        points = [
            (cx, cy - size),
            (cx + size, cy),
            (cx, cy + size),
            (cx - size, cy),
        ]
        pygame.draw.polygon(screen, GOLD_MID, points)
        pygame.draw.polygon(screen, GOLD_LIGHT, points, 2)
        pygame.draw.circle(screen, WHITE, (cx - 2, cy - 2), 2)

        # Кольцо-таймер
        rect = pygame.Rect(cx - CELL, cy - CELL, CELL * 2, CELL * 2)
        start_angle = -math.pi / 2
        end_angle = start_angle + 2 * math.pi * life_ratio
        if end_angle > start_angle:
            pygame.draw.arc(screen, GOLD_MID, rect, start_angle, end_angle, 2)

    def _draw_snake(self):
        n = len(self.snake)
        for i, (x, y) in enumerate(self.snake):
            t = i / max(n - 1, 1)
            r = int(GREEN_HEAD[0] * (1 - t) + GREEN_TAIL[0] * t)
            g = int(GREEN_HEAD[1] * (1 - t) + GREEN_TAIL[1] * t)
            b = int(GREEN_HEAD[2] * (1 - t) + GREEN_TAIL[2] * t)
            color = (r, g, b)

            pad = 1 if i == 0 else 2
            rect = pygame.Rect(
                x * CELL + pad,
                y * CELL + pad,
                CELL - pad * 2,
                CELL - pad * 2,
            )
            pygame.draw.rect(screen, color, rect, border_radius=5)

            if i == 0:
                cx = x * CELL + CELL // 2
                cy = y * CELL + CELL // 2
                dx, dy = self.direction
                ex, ey = dx * 3, dy * 3
                perp_x, perp_y = -dy * 4, dx * 4
                pygame.draw.circle(screen, BG_COLOR,
                                   (cx + ex + perp_x, cy + ey + perp_y), 2)
                pygame.draw.circle(screen, BG_COLOR,
                                   (cx + ex - perp_x, cy + ey - perp_y), 2)

    def _draw_teleport_effects(self, now):
        self.teleport_effects = [
            e for e in self.teleport_effects if now - e['start'] < 400
        ]
        for e in self.teleport_effects:
            age = (now - e['start']) / 400
            alpha = int(255 * (1 - age))
            size = int(CELL * (0.4 + age * 0.9))

            cx = e['x'] * CELL + CELL // 2
            cy = e['y'] * CELL + CELL // 2

            surf = pygame.Surface((size * 2 + 4, size * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*PORTAL_COLOR, alpha),
                               (size + 2, size + 2), size, 3)
            screen.blit(surf, (cx - size - 2, cy - size - 2))

    def _draw_hud(self):
        text = font_small.render(f"Счёт: {self.score}", True, WHITE)
        screen.blit(text, (10, 8))

        if self.bonus_score > 0:
            text2 = font_small.render(f"Бонусы: {self.bonus_score}", True, GOLD_MID)
            screen.blit(text2, (10, 34))

        if AUDIO_OK:
            hint = font_small.render("+/- громкость", True, (100, 100, 120))
            screen.blit(hint, (WIDTH - hint.get_width() - 10, 8))

    def _draw_pause_overlay(self):
        surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 140))
        screen.blit(surf, (0, 0))

        text = font_big.render("ПАУЗА", True, GREEN_HEAD)
        screen.blit(text, (WIDTH // 2 - text.get_width() // 2, HEIGHT // 2 - 40))

        text2 = font_small.render("Нажми ПРОБЕЛ, чтобы продолжить", True, WHITE)
        screen.blit(text2, (WIDTH // 2 - text2.get_width() // 2, HEIGHT // 2 + 20))

    def _draw_start_overlay(self):
        surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 160))
        screen.blit(surf, (0, 0))

        text = font_mid.render("Нажми любую стрелку", True, GREEN_HEAD)
        screen.blit(text, (WIDTH // 2 - text.get_width() // 2, HEIGHT // 2 - 30))

        text2 = font_small.render("🌀 Стены телепортируют на другую сторону", True, WHITE)
        screen.blit(text2, (WIDTH // 2 - text2.get_width() // 2, HEIGHT // 2 + 30))

    def _draw_game_over_overlay(self):
        surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 190))
        screen.blit(surf, (0, 0))

        text = font_big.render("Игра окончена", True, RED)
        screen.blit(text, (WIDTH // 2 - text.get_width() // 2, HEIGHT // 2 - 90))

        text2 = font_mid.render(f"Счёт: {self.score}", True, WHITE)
        screen.blit(text2, (WIDTH // 2 - text2.get_width() // 2, HEIGHT // 2 - 20))

        if self.bonus_score > 0:
            text3 = font_small.render(f"Поймано бонусов: {self.bonus_score}",
                                      True, GOLD_MID)
            screen.blit(text3, (WIDTH // 2 - text3.get_width() // 2, HEIGHT // 2 + 25))

        text4 = font_small.render("ПРОБЕЛ — новая игра    ESC — выход", True, WHITE)
        screen.blit(text4, (WIDTH // 2 - text4.get_width() // 2, HEIGHT // 2 + 80))


# ============================================================
#                       ГЛАВНЫЙ ЦИКЛ
# ============================================================
def main():
    game = SnakeGame()
    start_music()
    music_volume = MUSIC_VOLUME

    running = True

    while running:
        now = pygame.time.get_ticks()

        # ---------- События ----------
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                # Громкость музыки
                if event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    music_volume = min(1.0, music_volume + 0.1)
                    if AUDIO_OK:
                        pygame.mixer.music.set_volume(music_volume)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    music_volume = max(0.0, music_volume - 0.1)
                    if AUDIO_OK:
                        pygame.mixer.music.set_volume(music_volume)

                # Управление змейкой
                if not game.game_over:
                    if event.key in (pygame.K_UP, pygame.K_w):
                        game.set_direction(0, -1)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        game.set_direction(0, 1)
                    elif event.key in (pygame.K_LEFT, pygame.K_a):
                        game.set_direction(-1, 0)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        game.set_direction(1, 0)
                    elif event.key == pygame.K_SPACE:
                        game.paused = not game.paused
                        if game.paused:
                            music_pause()
                        else:
                            music_unpause()

                # Новая игра
                if game.game_over and event.key == pygame.K_SPACE:
                    game.reset()
                    music_unpause()

        # ---------- Логика ----------
        if not game.paused and not game.game_over:
            game.update_bonus(now)
            if now - game.last_move_time >= game.speed:
                game.update(now)
                game.last_move_time = now

        # ---------- Отрисовка ----------
        game.draw(now)
        pygame.display.flip()
        clock.tick(FPS)

    music_stop()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()