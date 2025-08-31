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
START_ALT = 2.0            # px above surface for stable start
IMPACT_EPS = 0.2           # tolerance inward from surface

# Satellite
SATELLITE_RADIUS = 5

# Time
TIME_SCALE = 1.0           # default runtime time-scale

# Atmosphere (simple)
BASE_AIR_DENSITY = 1.0     # surface density
SCALE_HEIGHT = 30.0        # px

# Starfield
NUM_STARS = 120

# Hotkey keycodes for brackets (ASCII)
KEY_LBRACKET = 91
KEY_RBRACKET = 93

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

# ---------- Mini graph helper ----------
def _draw_mini_graph(x, y, w, h, data, ymin, ymax, color=arcade.color.LIGHT_GRAY, title=""):
    # Frame
    arcade.draw_rectangle_outline(x + w / 2, y + h / 2, w, h, arcade.color.DIM_GRAY, 1)
    # Title inside the box
    if title:
        arcade.draw_text(title, x + 4, y + h - 14, arcade.color.WHITE, 12)

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

        # Mission Control parameters
        self.initial_speed = initial_speed
        self.launch_angle = launch_angle
        self.satellite_mass = satellite_mass
        self.drag_coefficient = drag_coefficient

        # Earth center
        self.earth_x = SCREEN_WIDTH // 2
        self.earth_y = SCREEN_HEIGHT // 2

        # Satellite state (start slightly above surface, on +X axis)
        self.satellite_x = self.earth_x + EARTH_RADIUS + START_ALT
        self.satellite_y = self.earth_y

        # Circular speed at launch radius
        r0 = math.hypot(self.satellite_x - self.earth_x, self.satellite_y - self.earth_y)
        self.v_circ = math.sqrt(MU / r0)
        self.v_circ_text = arcade.Text(
            f"v_circ @ launch: {self.v_circ:.2f} px/s",
            10, SCREEN_HEIGHT - 80, arcade.color.WHITE, 12
        )

        # Kinematics
        self.vx = 0.0
        self.vy = 0.0
        self.launched = False

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
        self.speed_text = arcade.Text("", 10, SCREEN_HEIGHT - 20, arcade.color.WHITE, 14)
        self.altitude_text = arcade.Text("", 10, SCREEN_HEIGHT - 40, arcade.color.WHITE, 14)
        self.orbit_count_text = arcade.Text("", 10, SCREEN_HEIGHT - 60, arcade.color.WHITE, 14)

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
            font_size=12
        )
        self.btn_slower = arcade.gui.UIFlatButton(text="–", width=30)
        self.btn_faster = arcade.gui.UIFlatButton(text="+", width=30)
        row = arcade.gui.UIBoxLayout(vertical=False, space_between=6)
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

    def on_show(self):
        arcade.set_background_color(arcade.color.BLACK)
        self.ui.enable()

    def on_hide_view(self):
        self.ui.disable()

    def on_draw(self):
        self.clear()

        # Stars
        for s in self.stars:
            a = 192 + int(63 * math.sin(self._twinkle_t * s["rate"] + s["phase"]))
            arcade.draw_point(s["x"], s["y"], (200, 200, 255, a), 2)

        # Earth
        arcade.draw_circle_filled(self.earth_x, self.earth_y, EARTH_RADIUS, arcade.color.DARK_GREEN)

        # Fading Orbit Trail
        for i, (tx, ty) in enumerate(self.trail):
            alpha = int(255 * (i / self.max_trail_length))
            arcade.draw_circle_filled(tx, ty, 2, (150, 150, 255, alpha))

        # Impact overlay
        if self.impact_detected:
            if self.impact_coords is not None:
                ix, iy = self.impact_coords
                arcade.draw_text(
                    f"Impact @ ({ix:.1f}, {iy:.1f}) bearing {self.impact_bearing_deg:.1f}°",
                    10, 70, arcade.color.WHITE, 14
                )
            arcade.draw_circle_filled(self.satellite_x, self.satellite_y, 10, arcade.color.RED_DEVIL)
            arcade.draw_text(f"Impact Time: {self.impact_time:.2f} sec",
                             10, 10, arcade.color.WHITE, 14)
            arcade.draw_text(f"Orbits completed: {self.orbit_count}",
                             10, 30, arcade.color.WHITE, 14)
            arcade.draw_text("Press R to return to Mission Control",
                             10, 50, arcade.color.LIGHT_GRAY, 14)

        # Satellite & velocity vector
        arcade.draw_circle_filled(self.satellite_x, self.satellite_y, SATELLITE_RADIUS, arcade.color.LIGHT_GRAY)
        if self.launched:
            arcade.draw_line(self.satellite_x, self.satellite_y,
                             self.satellite_x + self.vx * 10,
                             self.satellite_y + self.vy * 10,
                             arcade.color.YELLOW, 2)

        # HUD (when flying)
        if self.launched and not self.impact_detected:
            self.speed_text.draw()
            self.altitude_text.draw()
            self.orbit_count_text.draw()
            self.v_circ_text.draw()

        # --- Mini Graph ---
        plot_w, plot_h = 220, 80
        pad = 10
        px = SCREEN_WIDTH - plot_w - pad
        py1 = pad + plot_h + 20
        py0 = pad

        alt_max = max(150.0, (EARTH_RADIUS * 0.75) + 80.0)
        spd_max = max(3.0, 1.2 * self.v_circ)

        _draw_mini_graph(px, py1, plot_w, plot_h, self.history_alt, 0.0, alt_max,
                         arcade.color.LIGHT_GREEN, "Altitude")
        _draw_mini_graph(px, py0, plot_w, plot_h, self.history_speed, 0.0, spd_max,
                         arcade.color.ORANGE, "Speed")

        # UI overlay
        self.ui.draw()

    def on_update(self, delta_time):
        if not self.launched or self.impact_detected:
            return

        dt = delta_time * self.time_scale
        self.sim_time += dt
        self._twinkle_t += dt  # starfield time

        # Vector to Earth center
        dx = self.earth_x - self.satellite_x
        dy = self.earth_y - self.satellite_y
        r = math.hypot(dx, dy)

        # Impact check
        if r <= EARTH_RADIUS - IMPACT_EPS:
            self.launched = False
            self.impact_detected = True
            self.impact_time = self.sim_time
            ix = self.satellite_x - self.earth_x
            iy = self.satellite_y - self.earth_y
            self.impact_coords = (ix, iy)
            self.impact_bearing_deg = (math.degrees(math.atan2(iy, ix)) + 360.0) % 360.0
            print(f"Impact Detected after {self.orbit_count} orbit(s) at "
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

    # Time-scale UI handlers
    def _on_slow(self, *_):
        self.time_scale = clamp(round(self.time_scale / 1.25, 2), self.min_time_scale, self.max_time_scale)
        self.time_label.text = f"Time x{self.time_scale:.1f}"

    def _on_fast(self, *_):
        self.time_scale = clamp(round(self.time_scale * 1.25, 2), self.min_time_scale, self.max_time_scale)
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

        # Launch (SPACE) 
        if symbol == arcade.key.SPACE:
            if self.launched or self.impact_detected:
                return
            self.launched = True

            dx = self.satellite_x - self.earth_x
            dy = self.satellite_y - self.earth_y
            r = math.hypot(dx, dy)
            if r == 0.0:
                print("Satellite is at Earth's center! Cannot launch.")
                self.launched = False
                return
            
            # Radial and tangential unit vectors
            nx, ny = dx / r, dy / r
            tx, ty = -ny, nx  
            theta = math.radians(self.launch_angle)
            dir_x = math.cos(theta) * tx + math.sin(theta) * nx
            dir_y = math.cos(theta) * ty + math.sin(theta) * ny
            # Apply tangential initial velocity
            self.vx = self.initial_speed * dir_x
            self.vy = self.initial_speed * dir_y
            return

        # Time-scale hotkeys
        if symbol == KEY_LBRACKET:
            self._on_slow()
        elif symbol == KEY_RBRACKET:
            self._on_fast()
        elif symbol == arcade.key.BACKSLASH:
            self.time_scale = TIME_SCALE
            self.time_label.text = f"Time x{self.time_scale:.1f}"

# ---------- Mission Control ----------
class MissionControlView(arcade.View):
    def __init__(self):
        super().__init__()
        self.ui = arcade.gui.UIManager()
        self.ui.enable()
        self.v_box = arcade.gui.UIBoxLayout()

        # Defaults for surface launch
        self.speed_input = arcade.gui.UIInputText(width=200, text="1.98")
        self.mass_input  = arcade.gui.UIInputText(width=200, text="100")
        self.drag_input  = arcade.gui.UIInputText(width=200, text="0.0000")
        self.angle_input = arcade.gui.UIInputText(width=220, text="0")

        self.v_box.add(arcade.gui.UILabel(text="Initial Speed:"))
        self.v_box.add(self.speed_input)
        self.v_box.add(arcade.gui.UILabel(text="Satellite Mass:"))
        self.v_box.add(self.mass_input)
        self.v_box.add(arcade.gui.UILabel(text="Drag Coefficient:"))
        self.v_box.add(self.drag_input)
        self.v_box.add(arcade.gui.UILabel(text="Launch Angle (°):"))
        self.v_box.add(self.angle_input)

        launch_button = arcade.gui.UIFlatButton(text="Launch Simulation", width=200)
        launch_button.on_click = self.on_launch
        self.v_box.add(launch_button)

        self.ui.add(arcade.gui.UIAnchorWidget(anchor_x="center_x", anchor_y="center_y", child=self.v_box))

    def on_show(self):
        arcade.set_background_color(arcade.color.DARK_BLUE_GRAY)

    def on_draw(self):
        self.clear()
        self.ui.draw()

    def on_launch(self, event):
        try:
            speed = float(self.speed_input.text)
            mass  = float(self.mass_input.text)
            drag  = float(self.drag_input.text)
            angle = float(self.angle_input.text)
            self.window.show_view(OrbitView(speed, angle, mass, drag))
        except ValueError:
            print("Please enter valid numerical values.")

# ---------- Main ----------
def main():
    window = arcade.Window(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
    window.show_view(MissionControlView())
    arcade.run()

if __name__ == "__main__":
    main()