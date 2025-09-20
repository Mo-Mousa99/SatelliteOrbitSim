import math
import random
import arcade
import arcade.gui

# ---------- Constants ----------
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
SCREEN_TITLE = "Satellite Orbit Simulator"

# Earth / Gravity (px units)
EARTH_RADIUS = 100
MU = 400.0                 # px^3/s^2 (v_circ ~ 2 px/s at r=100)
IMPACT_EPS = 0.2           # tolerance inward from surface

# Satellite
SATELLITE_RADIUS = 5
LAUNCH_BEARING_DEG = 0.0
LAUNCH_GRACE_FRAMES = 2

# Time
TIME_SCALE = 1.0           # default runtime time-scale

# Atmosphere (simple)
BASE_AIR_DENSITY = 1.0     # surface density
SCALE_HEIGHT = 25.0        # px

# Starfield
NUM_STARS = 120

# Font
FONT_PATH = "assets/fonts/PressStart2P-Regular.ttf"
FONT_NAME = "Press Start 2P"
arcade.load_font(FONT_PATH)

def clamp(v, lo, hi):
    return max(lo, min(hi, v))
# Globe Texture Helper
def load_grid_textures(file_path, cell_w, cell_h, cols, rows, margin=0, spacing=0):
    frames = []
    for r in range(rows):
        for c in range(cols):
            x = margin + c * (cell_w + spacing)
            y= margin + r * (cell_h + spacing)
            frames.append(arcade.load_texture(file_path, x, y, cell_w, cell_h))
    return frames

# --- Mini graph helper ---
def _draw_mini_graph(x, y, w, h, data, ymin, ymax, color=arcade.color.LIGHT_GRAY, title=""):
    # Frame
    arcade.draw_rectangle_outline(x + w / 2, y + h / 2, w, h, arcade.color.DIM_GRAY, 1)
    # Title inside the box
    if title:
        arcade.draw_text(title, x + 4, y + h - 14, arcade.color.WHITE, 10, font_name=FONT_NAME)

    if not data or len(data) < 2:
        return

    step_x = w / max(1, len(data) - 1)

    def norm(v):
        if ymax == ymin:
            return 0.0
        # clamp to [0, 1] so line stays inside the box
        return clamp((v - ymin) / (ymax - ymin), 0.0, 1.0)

    pts = []
    for i, v in enumerate(data):
        px = x + i * step_x
        py = y + norm(v) * h
        pts.append((px, py))
    arcade.draw_line_strip(pts, color, 1)

# ---------- Orbit View ----------
class OrbitView(arcade.View):
    def __init__(self, initial_speed, launch_angle, satellite_mass, drag_coefficient):
        super().__init__()


        sheet_path = "assets/earth/earth_rot_4x3.png"
        CELL_W, CELL_H = 69, 69
        COLS, ROWS = 4, 3
        self.earth_frames = load_grid_textures(sheet_path, CELL_W, CELL_H, COLS, ROWS)
        self.has_earth_frames = len(self.earth_frames) > 0

        self.earth_fps = 0.5
        self._earth_anim_accum = 0.0
        self._earth_frame_idx = 0

        self.portrait_frames = load_grid_textures(
            "assets/portraits/pilot.png",
            128, 128,
            4, 1)
        self.current_portrait_idx = 0

        self.render_mode = "orbit"

        self.world_cam = arcade.Camera(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.ui_cam = arcade.Camera(SCREEN_WIDTH, SCREEN_HEIGHT)

        self.map_tex = arcade.load_texture("assets/maps/pixel_art_map.png")
        self.pin_tex = arcade.load_texture("assets/maps/pixel_art_pin.png")

        # Mission Control parameters
        self.initial_speed = initial_speed
        self.launch_angle = launch_angle
        self.satellite_mass = satellite_mass
        self.drag_coefficient = drag_coefficient

        # Earth center
        self.earth_x = SCREEN_WIDTH // 2
        self.earth_y = SCREEN_HEIGHT // 2
        
        # --- Launch pad on the rim ---
        phi = math.radians(LAUNCH_BEARING_DEG)
        pad_nx = math.cos(phi)
        pad_ny = math.sin(phi)

        # Satellite state
        self.satellite_x = self.earth_x + EARTH_RADIUS * pad_nx
        self.satellite_y = self.earth_y + EARTH_RADIUS * pad_ny

        # Circular speed at launch radius
        r0 = EARTH_RADIUS
        self.v_circ = math.sqrt(MU / r0)
        self.v_circ_text = arcade.Text(
            f"v_circ @ launch: {self.v_circ:.2f} px/s",
            10, SCREEN_HEIGHT - 80, arcade.color.WHITE, 10, font_name=FONT_NAME
        )

        # Kinematics
        self.vx = 0.0
        self.vy = 0.0
        self.launched = False
        self._frames_since_launch = 0

        # Trail
        self.trail = []
        self.max_trail_length = 350

        # Impact and Simulation Time
        self.impact_detected = False
        self.impact_time = None
        self.impact_coords = None            # (ix, iy) relative to center, frozen at impact
        self.impact_bearing_deg = None
        self.sim_time = 0.0

        # Orbit Track
        self.total_angle_travelled = 0.0
        self.previous_angle = None
        self.orbit_count = 0

        # Informative Graph
        self.history_t = []
        self.history_alt = []
        self.history_speed = []
        self.max_hist = 400

        # HUD text objects
        self.speed_text = arcade.Text("", 10, SCREEN_HEIGHT - 20, arcade.color.WHITE, 10, font_name=FONT_NAME)
        self.altitude_text = arcade.Text("", 10, SCREEN_HEIGHT - 40, arcade.color.WHITE, 10, font_name=FONT_NAME)
        self.orbit_count_text = arcade.Text("", 10, SCREEN_HEIGHT - 60, arcade.color.WHITE, 10, font_name=FONT_NAME)

    
        # --- Starfield ---
        self.stars = [{
            "x": random.randint(0, SCREEN_WIDTH),
            "y": random.randint(0, SCREEN_HEIGHT),
            "phase": random.random() * 2 * math.pi,
            "rate": 0.5 + random.random() * 2.0
        } for _ in range(NUM_STARS)]
        self._twinkle_t = 0.0

        # --- Time scale & UI ---
        self.time_scale = TIME_SCALE
        self.min_time_scale = 0.1
        self.max_time_scale = 20.0

        self.ui = arcade.gui.UIManager()
        self.vbox = arcade.gui.UIBoxLayout(space_between=6)
        self.time_label = arcade.gui.UILabel(
            text=f"Time x{self.time_scale:.1f}",
            text_color=arcade.color.WHITE,
            font_size=12,
            font_name=FONT_NAME
        )

        self.tex_minus = arcade.load_texture("assets/ui/MINUS.png")
        self.tex_plus = arcade.load_texture("assets/ui/PLUS.png")

        row = arcade.gui.UIBoxLayout(vertical=False, space_between=6)
        self.btn_slower = arcade.gui.UITextureButton(
            width=30, height=30,
            texture=self.tex_minus
        )
        self.btn_faster = arcade.gui.UITextureButton(
            width=30, height=30,
            texture=self.tex_plus
        )
        row.add(self.btn_slower)
        row.add(self.btn_faster)
        self.vbox.add(self.time_label)
        self.vbox.add(row)
        self.btn_slower.on_click = self._on_slow
        self.btn_faster.on_click = self._on_fast
        self.anchor = arcade.gui.UIAnchorWidget(
            anchor_x="left", anchor_y="top", align_x=12, align_y=-92, child=self.vbox
        )
        self.ui.add(self.anchor)

        # --- Control Bar ---
        self.icon_tex = {
            "map": arcade.load_texture("assets/ui/M.png"),
            "orbit": arcade.load_texture("assets/ui/O.png"),
            "reset": arcade.load_texture("assets/ui/R.png"),
        }

        self.icon_size = 28
        self.icon_gap = 100
        self.controls_y = 50

        self.launch_hint = arcade.Text(
            "PRESS SPACE TO LAUNCH",
            SCREEN_WIDTH // 2, self.controls_y + 30,
            arcade.color.LIGHT_GREEN, 12,
            font_name=FONT_NAME,
            anchor_x="center"
        )

    def _draw_control_icon(self, x, y, tex, key_label):
        arcade.draw_texture_rectangle(x, y, self.icon_size, self.icon_size, tex)

        arcade.draw_text(
            key_label, x, y - (self.icon_size // 2) - 8,
            arcade.color.LIGHT_GREEN, 10,
            font_name=FONT_NAME,
            anchor_x="center", anchor_y="top"
        )

        # Bearing
    def _current_bearing_deg(self) -> float:
        ix = self.satellite_x - self.earth_x
        iy = self.satellite_y - self.earth_y
        return (math.degrees(math.atan2(iy, ix)) + 360.0) % 360.0

    def on_show(self):
        arcade.set_background_color(arcade.color.BLACK)
        self.ui.enable()

    def on_hide_view(self):
        self.ui.disable()

    def _bearing_to_map_xy(self, bearing_deg, map_w, map_h):
        lon = bearing_deg
        u = (lon % 360.0) / 360.0
        x = int(u * map_w)
        y = int(map_h * 0.5)
        return x,y
    
    def _draw_orbit_view(self):

        for s in self.stars:
            a = 192 + int(63 * math.sin(self._twinkle_t * s["rate"] + s["phase"]))
            arcade.draw_point (s["x"], s["y"], (200, 200, 255, a), 2)


        if self.has_earth_frames:
            size = EARTH_RADIUS * 2
            tex = self.earth_frames[self._earth_frame_idx]
            arcade.draw_texture_rectangle(self.earth_x, self.earth_y, size, size, tex)
        else:
            arcade.draw_circle_filled(self.earth_x, self.earth_y, EARTH_RADIUS, arcade.color.DARK_GREEN)
            
        for i, (tx, ty) in enumerate(self.trail):
            alpha = int(255 * (i / self.max_trail_length))
            arcade.draw_circle_filled(tx, ty, 2, (150, 150, 255, alpha))
        
        arcade.draw_circle_filled(self.satellite_x, self.satellite_y, SATELLITE_RADIUS, arcade.color.LIGHT_GRAY)
        if self.launched:
            arcade.draw_line(self.satellite_x, self.satellite_y,
                             self.satellite_x + self.vx * 10,
                             self.satellite_y + self.vy * 10,
                             arcade.color.YELLOW, 2)
            

    def _draw_map_view(self):
        map_w, map_h = self.map_tex.width, self.map_tex.height
        mx = (SCREEN_WIDTH - map_w)  //2
        my = (SCREEN_HEIGHT - map_h) //2
        arcade.draw_lrwh_rectangle_textured(mx, my, map_w, map_h, self.map_tex)

        cur_bearing = self._current_bearing_deg()
        cx, cy = self._bearing_to_map_xy(cur_bearing, map_w, map_h)
        arcade.draw_circle_filled(mx + cx, my + cy, 6, arcade.color.LIGHT_GRAY)
        if self.impact_detected and self.impact_bearing_deg is not None:
            ix, iy = self._bearing_to_map_xy(self.impact_bearing_deg, map_w, map_h)
            arcade.draw_texture_rectangle(mx + ix, my + iy, 14, 14, self.pin_tex)

    def on_draw(self):
        self.clear()

        self.world_cam.use()
        if self.render_mode == "orbit":
            self._draw_orbit_view()
        elif self.render_mode == "map":
            self._draw_map_view()

        self.ui_cam.use()

        # --- Mini Graph ---
        plot_w, plot_h = 220, 80
        pad = 10
        px = SCREEN_WIDTH - plot_w - pad
        py1 = pad + plot_h + 20
        py0 = pad
        alt_max = max(150.0, (EARTH_RADIUS * 0.75) + 80.0)
        spd_max = max(3.0, 1.2 * self.v_circ)

        # HUD (when flying)
        if self.launched and not self.impact_detected and self.render_mode == "orbit":
            _draw_mini_graph(px, py1, plot_w, plot_h, self.history_alt, 0.0, alt_max,
                             arcade.color.LIGHT_GREEN, "Altitude")
            _draw_mini_graph(px, py0, plot_w, plot_h, self.history_speed, 0.0, spd_max,
                             arcade.color.ORANGE, "Speed")
            self.speed_text.draw()
            self.altitude_text.draw()
            self.orbit_count_text.draw()
            self.v_circ_text.draw()

        if self.render_mode == "orbit":
            frame_idx = 3 if self.impact_detected else self.current_portrait_idx
            tex = self.portrait_frames[frame_idx]

            portrait_w = 120
            portrait_h = 120
            margin = 10
            portrait_x = px + plot_w / 2
            portrait_y = py1 + plot_h + margin + portrait_h / 2 
            arcade.draw_texture_rectangle(portrait_x, portrait_y, portrait_w, portrait_h, tex)

        # UI overlay
        self.ui.draw()

        # --- Control Bar ---
        icons = ["map", "orbit", "reset"]
        labels = ["Map", "Orbit", "Return to MM"]

        total_w = len(icons) * self.icon_size + (len(icons) - 1) * self.icon_gap
        start_x = (SCREEN_WIDTH - total_w) // 8 + self.icon_size // 2
        x = start_x
        
        if not self.impact_detected:
            for name, lab in zip(icons, labels):
                tex = self.icon_tex[name]
                self._draw_control_icon(x, self.controls_y, tex, lab)
                x += self.icon_size + self.icon_gap

        if (not self.launched) and (not self.impact_detected):
            self.launch_hint.draw()


        # Impact overlay
        if self.render_mode == "orbit" and self.impact_detected:
            if self.impact_coords is not None:
                ix, iy = self.impact_coords
                arcade.draw_text(
                    f"Impact @ ({ix:.1f}, {iy:.1f}) bearing {self.impact_bearing_deg:.1f}°",
                    10, 70, arcade.color.WHITE, 14, font_name=FONT_NAME
                )
            arcade.draw_circle_filled(self.satellite_x, self.satellite_y, 10, arcade.color.RED_DEVIL)
            arcade.draw_text(f"Impact Time: {self.impact_time:.2f} sec",
                             10, 10, arcade.color.WHITE, 14, font_name=FONT_NAME)
            arcade.draw_text(f"Orbits completed: {self.orbit_count}",
                             10, 30, arcade.color.WHITE, 14, font_name=FONT_NAME)
            arcade.draw_text("Press R to return to Mission Control",
                             10, 50, arcade.color.LIGHT_GRAY, 14, font_name=FONT_NAME)
            

    def on_update(self, delta_time):
        if not self.launched or self.impact_detected:
            return

        dt = delta_time * self.time_scale
        self.sim_time += dt
        self._twinkle_t += dt  # starfield time

        if self.has_earth_frames:
            self._earth_anim_accum += dt * self.earth_fps
            if self._earth_anim_accum >= 1.0:
                steps = int(self._earth_anim_accum)
                self._earth_anim_accum -= steps
                n = len(self.earth_frames)
                self._earth_frame_idx = (self._earth_frame_idx + steps) % n

        # Vector to Earth center
        dx = self.earth_x - self.satellite_x
        dy = self.earth_y - self.satellite_y
        r = math.hypot(dx, dy)

        # Impact check
        if self._frames_since_launch >= LAUNCH_GRACE_FRAMES:
            if r <= EARTH_RADIUS - IMPACT_EPS:
                self.launched = False
                self.impact_detected = True
                self.impact_time = self.sim_time
                ix = self.satellite_x - self.earth_x
                iy = self.satellite_y - self.earth_y
                self.impact_coords = (ix, iy)
                self.impact_bearing_deg = (math.degrees(math.atan2(iy, ix)) + 360.0) % 360.0
                self.current_portrait_idx = 3
                print(f"Impact Detected after {self.orbit_count} orbit(s) at"
                      f"({ix:.1f}, {iy:.1f}), bearing {self.impact_bearing_deg:.1f}°")
                return

        # Gravity
        ax = MU * dx / (r ** 3)
        ay = MU * dy / (r ** 3)

        # Drag (with simple exponential atmosphere)
        h = r - EARTH_RADIUS
        rho = BASE_AIR_DENSITY * math.exp(-max(h, 0.0) / SCALE_HEIGHT)

        v = math.hypot(self.vx, self.vy)
        if v > 0.0:
            drag_acc = (self.drag_coefficient / max(self.satellite_mass, 1e-8)) * rho * (v * v)
            ax += -drag_acc * (self.vx / v)
            ay += -drag_acc * (self.vy / v)

        # Pilot State
        if h < 10.0:
            self.current_portrait_idx = 2
        else:
            self.current_portrait_idx = 1 if h > 20.0 else 0

        # Integrate (semi-implicit Euler)
        self.vx += ax * dt
        self.vy += ay * dt
        self.satellite_x += self.vx * dt
        self.satellite_y += self.vy * dt

        # --- Orbit counting ---
        angle = math.atan2(self.earth_y - self.satellite_y, self.earth_x - self.satellite_x)
        if self.previous_angle is not None:
            dtheta = angle - self.previous_angle
            if dtheta > math.pi:
                dtheta -= 2 * math.pi
            elif dtheta < -math.pi:
                dtheta += 2 * math.pi
            self.total_angle_travelled += abs(dtheta)
            if self.total_angle_travelled >= 2 * math.pi:
                self.orbit_count += 1
                self.total_angle_travelled = 0.0
        self.previous_angle = angle

        #  --- Graph History ---
        self.history_t.append(self.sim_time)
        self.history_alt.append(h)
        self.history_speed.append(v)
        if len(self.history_t) > self.max_hist:
            self.history_t.pop(0)
            self.history_alt.pop(0)
            self.history_speed.pop(0)

        # --- Trail & HUD ---
        self.trail.append((self.satellite_x, self.satellite_y))
        if len(self.trail) > self.max_trail_length:
            self.trail.pop(0)

        self.speed_text.text = f"Speed: {v:.2f} px/s"
        self.altitude_text.text = f"Altitude: {h:.2f} px"
        self.orbit_count_text.text = f"Orbits: {self.orbit_count}"

        self._frames_since_launch += 1


    # Time-scale UI handlers
    def _on_slow(self, *_):
        self.time_scale = clamp(round(self.time_scale / 2, 2), self.min_time_scale, self.max_time_scale)
        self.time_label.text = f"Time x{self.time_scale:.1f}"

    def _on_fast(self, *_):
        self.time_scale = clamp(round(self.time_scale * 1.5, 2), self.min_time_scale, self.max_time_scale)
        self.time_label.text = f"Time x{self.time_scale:.1f}"

    # Hotkeys
    def on_key_press(self, symbol, modifiers):
        # Restart to Mission Control
        if symbol == arcade.key.R:
            try:
                self.ui.disable()
            except Exception:
                pass
            self.window.show_view(MissionControlView())
            return

        # --- Launch Logic --- 
        if symbol == arcade.key.SPACE:
            if self.launched or self.impact_detected:
                return
            self.launched = True
            self._frames_since_launch = 0

            dx = self.satellite_x - self.earth_x
            dy = self.satellite_y - self.earth_y
            r = math.hypot(dx, dy)
            if r == 0.0:
                print("Satellite is at Earth's center! Cannot launch.")
                self.launched = False
                return
            
            # Radial and tangential unit vectors, where n = outward radial, t = tangent
            nx, ny = dx / r, dy / r
            tx, ty = -ny, nx
            # Angle convention: Where 0° = tangent, 90° = radial outward
            theta = math.radians(self.launch_angle)
            dir_x = math.cos(theta) * tx + math.sin(theta) * nx
            dir_y = math.cos(theta) * ty + math.sin(theta) * ny
            # Apply tangential initial velocity
            self.vx = self.initial_speed * dir_x
            self.vy = self.initial_speed * dir_y
            return

        # Time-scale hotkeys
        if symbol == arcade.key.MINUS or symbol == arcade.key.NUM_SUBTRACT:
            self._on_slow()
        elif symbol == arcade.key.EQUAL or symbol == arcade.key.NUM_ADD:
            self._on_fast()
        elif symbol == arcade.key.BACKSLASH:
            self.time_scale = TIME_SCALE
            self.time_label.text = f"Time x{self.time_scale:.1f}"

        if symbol == arcade.key.O:
            self.render_mode = "orbit"
        elif symbol == arcade.key.M:
            self.render_mode = "map"

# ---------- Mission Control ----------
class MissionControlView(arcade.View):
    def __init__(self):
        super().__init__()

        # Background PNG
        self.bg_tex = arcade.load_texture("assets/ui/mission_control.png")

        self.cat_frames = load_grid_textures("assets/ui/Sleepy_Pilot.png", 64, 64, 2, 1)
        self.cat_frame_idx = 0
        self.cat_anim_accum = 0.0
        self.cat_fps = 1.0  

        # UI Manager
        self.ui = arcade.gui.UIManager()
        self.ui.enable()
        
        # Error banner
        self.error_text = arcade.Text(
            "",
            SCREEN_WIDTH // 2, 100,
            arcade.color.LIGHT_GREEN, 14,
            font_name=FONT_NAME,
            anchor_x="center"
        )
        self._error_timer = 0.0

        # Input fields
        self.speed_input = arcade.gui.UIInputText(
            width=100, text="2.02",
            font_name=FONT_NAME, font_size=10, text_color=arcade.color.LIGHT_GREEN
        )
        self.mass_input = arcade.gui.UIInputText(
            width=140, text="100",
            font_name=FONT_NAME, font_size=10, text_color=arcade.color.LIGHT_GREEN
        )
        self.drag_input = arcade.gui.UIInputText(
            width=140, text="0.00",
            font_name=FONT_NAME, font_size=10, text_color=arcade.color.LIGHT_GREEN
        )
        self.angle_input = arcade.gui.UIInputText(
            width=140, text="0",
            font_name=FONT_NAME, font_size=10, text_color=arcade.color.LIGHT_GREEN
        )

        # Launch button with normal + pressed icons
        normal_tex = arcade.load_texture("assets/ui/Icon1.png")
        pressed_tex = arcade.load_texture("assets/ui/IconPressed1.png")
        self.launch_button = arcade.gui.UITextureButton(
            x=520, y=150, width=30, height=27,
            texture=normal_tex, texture_pressed=pressed_tex
        )
        self.launch_button.on_click = self.on_launch

        self.ui.add(arcade.gui.UIAnchorWidget(anchor_x="left", anchor_y="bottom",
                                              align_x=280, align_y=310, child=self.speed_input))
        self.ui.add(arcade.gui.UIAnchorWidget(anchor_x="left", anchor_y="bottom",
                                              align_x=390, align_y=310, child=self.mass_input))
        self.ui.add(arcade.gui.UIAnchorWidget(anchor_x="left", anchor_y="bottom",
                                              align_x=390, align_y=260, child=self.drag_input))
        self.ui.add(arcade.gui.UIAnchorWidget(anchor_x="left", anchor_y="bottom",
                                              align_x=290, align_y=235, child=self.angle_input))
        self.ui.add(arcade.gui.UIAnchorWidget(anchor_x="left", anchor_y="bottom",
                                              align_x=450, align_y=260, child=self.launch_button))

        # Labels drawn
        self.labels = [
            arcade.Text("SPEED", 281, 340 + 30, arcade.color.LIGHT_GREEN, 10, font_name=FONT_NAME),
            arcade.Text("MASS", 390, 340 + 30, arcade.color.LIGHT_GREEN, 10, font_name=FONT_NAME),
            arcade.Text("DRAG", 390, 290 + 30, arcade.color.LIGHT_GREEN, 10, font_name=FONT_NAME),
            arcade.Text("ANGLE", 281, 285 + 30, arcade.color.LIGHT_GREEN, 10, font_name=FONT_NAME),
            arcade.Text("LAUNCH", 380, 235 + 30, arcade.color.LIGHT_GREEN, 9, font_name=FONT_NAME)
        ]

        self.title_text = arcade.Text("MISSION CONTROL", 24, SCREEN_HEIGHT - 48,
                                      arcade.color.LIGHT_GREEN, 16, font_name=FONT_NAME)
        

    def _show_error(self, msg: str, seconds: float = 3.0):
        self.error_text.text = msg
        self._error_timer = seconds

    def on_update(self, delta_time: float):
        if self._error_timer > 0:
            self._error_timer = max(0.0, self._error_timer - delta_time)

        self.cat_anim_accum += delta_time * self.cat_fps
        if self.cat_anim_accum >= 1.0:
            self.cat_anim_accum = 0.0
            self.cat_frame_idx = (self.cat_frame_idx + 1) % len(self.cat_frames)

    def on_show(self):
        arcade.set_background_color(arcade.color.DARK_BLUE_GRAY)

    def on_draw(self):
        self.clear()
        arcade.draw_lrwh_rectangle_textured(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, self.bg_tex)
        arcade.draw_texture_rectangle(250, 200, 64, 64, self.cat_frames[self.cat_frame_idx])

        self.title_text.draw()
        for lbl in self.labels:
            lbl.draw()

        self.ui.draw()

        if self._error_timer > 0:
            pad_x, pad_y = 12, 8
            tw = self.error_text.content_width
            th = self.error_text.content_height
            cx, cy = self.error_text.x, self.error_text.y
            arcade.draw_rectangle_filled(
                cx, cy, tw + pad_x * 2, th + pad_y * 2, (0, 0, 0, 100)
            )
            self.error_text.draw()

    def on_launch(self, event):
        try:
            speed = float(self.speed_input.text)
            mass  = float(self.mass_input.text)
            drag  = float(self.drag_input.text)
            angle = float(self.angle_input.text)
            self.window.show_view(OrbitView(speed, angle, mass, drag))
        except ValueError:
            self._show_error(f"Invalid input!", seconds = 3.0)

# ---------- Main ----------
def main():
    window = arcade.Window(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
    window.show_view(MissionControlView())
    arcade.run()

if __name__ == "__main__":
    main()