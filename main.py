import arcade
import arcade.gui
import math

# set screen dimensions (constants)
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
SCREEN_TITLE = "Satellite Orbit Simulator"
#Earth(Constant)
EARTH_RADIUS = 100
EARTH_MASS = 5.972e24 #Will be used later
MU = 400.0
IMPACT_EPS = 0.5
#Satellite(Constant)
SATELLITE_RADIUS = 5
INITIAL_DISTANCE = 200 #From Earth center
TIME_SCALE = 1.0
START_ALT = 2.0
#Atmospheric Factors
BASE_AIR_DENSITY = 1.0 #At Earth Surface
SCALE_HEIGHT = 30 # How fast Atmosphere thins

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

#Orbit View
class OrbitView(arcade.View):
    def __init__(self, initial_speed, launch_angle, satellite_mass, drag_coefficient):
        super().__init__()

        #User-defined values from Mission Control
        self.initial_speed = initial_speed
        self.launch_angle = launch_angle
        self.satellite_mass = satellite_mass
        self.drag_coefficient = drag_coefficient
        #Earth Center
        self.earth_x = SCREEN_WIDTH // 2
        self.earth_y = SCREEN_HEIGHT // 2

        #Satellite State
        self.satellite_x = self.earth_x + EARTH_RADIUS + START_ALT
        self.satellite_y = self.earth_y

        #Initial Velocity
        self.vx = 0
        self.vy = 0
        self.launched = False

        #Trail Buffer
        self.trail = []
        self.max_trail_length = 500
        
        #Impact and Simulation Time
        self.impact_detected = False
        self.impact_time = None
        self.sim_time = 0 #This tracks total simulation time

        #Orbit Track
        self.total_angle_travelled = 0
        self.previous_angle = None
        self.orbit_count = 0

        #Hud State
        self.speed_text = arcade.Text("", 10, SCREEN_HEIGHT - 20, color= arcade.color.WHITE, font_size= 14)
        self.altitude_text = arcade.Text("", 10, SCREEN_HEIGHT - 40, color= arcade.color.WHITE, font_size= 14)
        self.orbit_count_text = arcade.Text("", 10, SCREEN_HEIGHT - 60, color= arcade.color.WHITE, font_size= 14)

        # --- Time scale ---
        self.time_scale = TIME_SCALE  # start from global default
        self.min_time_scale = 0.1
        self.max_time_scale = 20.0

        # --- Small UI overlay for time scale ---
        self.ui = arcade.gui.UIManager()
        self.vbox = arcade.gui.UIBoxLayout(space_between=6)

        self.time_label = arcade.gui.UILabel(text=f"Time x{self.time_scale:.1f}", text_color=arcade.color.WHITE, font_size=12)
        self.btn_slower = arcade.gui.UIFlatButton(text="–", width=30)
        self.btn_faster = arcade.gui.UIFlatButton(text="+", width=30)
        row = arcade.gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self.btn_slower)
        row.add(self.btn_faster)

        self.vbox.add(self.time_label)
        self.vbox.add(row)

        # hook up events
        self.btn_slower.on_click = self._on_slow
        self.btn_faster.on_click = self._on_fast

        # Anchor top-left
        self.anchor = arcade.gui.UIAnchorWidget(anchor_x="left", anchor_y="top", align_x=12, align_y=-12, child=self.vbox)
        self.ui.add(self.anchor)

    def on_show(self):
        arcade.set_background_color(arcade.color.BLACK)
        self.ui.enable()
    
    def on_hide_view(self):
        self.ui.disable()

    def on_draw(self):
        self.clear()
        #Placeholder Earth
        arcade.draw_circle_filled(self.earth_x, self.earth_y, EARTH_RADIUS, arcade.color.DARK_GREEN)
        

        #Fading Orbit Trail
        for i, (tx, ty) in enumerate(self.trail):
            alpha = int(255* (i / self.max_trail_length))
            arcade.draw_circle_filled(tx, ty, 2, (150, 150, 255, alpha))

        if self.impact_detected:
            arcade.draw_circle_filled(self.satellite_x, self.satellite_y, 10, arcade.color.RED_DEVIL)
            arcade.draw_text(f"Impact Time: {self.impact_time:.2f} sec",
                              10, 10, arcade.color.WHITE, 14)

        #Placeholder Satellite
        arcade.draw_circle_filled(self.satellite_x, self.satellite_y, SATELLITE_RADIUS, arcade.color.LIGHT_GRAY)

        #Draw velocity vector
        if self.launched:
            arcade.draw_line(self.satellite_x, self.satellite_y,
                             self.satellite_x + self.vx * 10,
                             self.satellite_y + self.vy * 10,
                             arcade.color.YELLOW, 2)
            
        if self.launched and not self.impact_detected:
            self.speed_text.draw()
            self.altitude_text.draw()
            self.orbit_count_text.draw()

        self.ui.draw()

    def on_update(self, delta_time):
        if not self.launched or self.impact_detected:
            return
        
        dt = delta_time * self.time_scale
        self.sim_time += dt

        # Vector to Earth center
        dx = self.earth_x - self.satellite_x
        dy = self.earth_y - self.satellite_y
        r  = math.hypot(dx, dy)
        
        # Impact check
        if r <= (EARTH_RADIUS + 0.0) - IMPACT_EPS:
         print("Impact Detected!")
         self.launched = False
         self.impact_detected = True
         self.impact_time = self.sim_time
         return
        
        # --- Gravity 
        ax =  MU * dx / (r**3)
        ay =  MU * dy / (r**3)
        
        # altitude from surface:
        h = r - EARTH_RADIUS
        rho = BASE_AIR_DENSITY * math.exp(-max(h, 0.0) / SCALE_HEIGHT)
        
        v = math.hypot(self.vx, self.vy)
        if v > 0:
            # Acceleration magnitude due to drag
            # Scale by 1/mass so heavy satellites are less affected
            drag_acc = (self.drag_coefficient / max(self.satellite_mass, 1e-8)) * rho * (v * v)
            ax += -drag_acc * (self.vx / v)
            ay += -drag_acc * (self.vy / v)
        
        # --- Integrate (symplectic/semi-implicit Euler)
        self.vx += ax * dt
        self.vy += ay * dt

        self.satellite_x += self.vx * dt
        self.satellite_y += self.vy * dt

        # --- Orbit counting
        angle = math.atan2(self.earth_y - self.satellite_y, self.earth_x - self.satellite_x)
        if self.previous_angle is not None:
            dtheta = angle - self.previous_angle
            if dtheta > math.pi: dtheta -= 2 * math.pi
            elif dtheta < -math.pi: dtheta += 2 * math.pi
            self.total_angle_travelled += abs(dtheta)
            if self.total_angle_travelled >= 2 * math.pi:
                self.orbit_count += 1
                self.total_angle_travelled = 0.0

        self.previous_angle = angle

        # --- Trail & HUD
        self.trail.append((self.satellite_x, self.satellite_y))
        if len(self.trail) > self.max_trail_length:
         self.trail.pop(0)

        self.speed = v  # px/s
        self.altitude = h
        self.speed_text.text = f"Speed: {self.speed:.2f} px/s"
        self.altitude_text.text = f"Altitude: {self.altitude:.2f} px"
        self.orbit_count_text.text = f"Orbits: {self.orbit_count}"

    def _on_slow(self, *_):
        self.time_scale = clamp(round(self.time_scale/ 1.25, 2), self.min_time_scale, self.max_time_scale)
        self.time_label.text = f"Time x{self.time_scale:.1f}"

    def _on_fast(self, *_):
        self.time_scale = clamp(round(self.time_scale* 1.25, 2), self.min_time_scale, self.max_time_scale)
        self.time_label.text = f"Time x{self.time_scale:.1f}"

        
    def on_key_press(self, symbol, modifiers):
        if symbol == arcade.key.SPACE:
            if self.launched or self.impact_detected:
                return
            self.launched = True
        elif symbol == 91:
            self._on_slow()
        elif symbol == 93:
            self._on_fast()
        elif symbol == arcade.key.BACKSLASH:
            self.time_scale = TIME_SCALE
            self.time_label.text = f"Time x{self.time_scale:.1f}"

            # Vector from Earth to satellite
        dx = self.satellite_x - self.earth_x
        dy = self.satellite_y - self.earth_y
        r = math.hypot(dx, dy)

        if r == 0:
            print("Satellite is at Earth's center! Cannot launch.")
            self.launched = False
            return

        # Radial and tangential unit vectors
        nx, ny = dx / r, dy / r
        tx, ty = -ny, nx

        # User angle: 0 = tangent, 90+ = radial outward
        theta = math.radians(self.launch_angle)
        dir_x = math.cos(theta) * tx + math.sin(theta) * nx
        dir_y = math.cos(theta) * ty + math.sin(theta) * ny

        # Apply tangential initial velocity
        self.vx = self.initial_speed * dir_x
        self.vy = self.initial_speed * dir_y

        
#Mission Control
class MissionControlView(arcade.View):
    def __init__(self):
        super().__init__()
        self.ui = arcade.gui.UIManager()
        self.ui.enable()
        self.v_box = arcade.gui.UIBoxLayout()

        #Input Widgets
        self.speed_input = arcade.gui.UIInputText(width=200, text="1.98")
        self.mass_input = arcade.gui.UIInputText(width=200, text="100")
        self.drag_input = arcade.gui.UIInputText(width=200, text="0.0000")
        self.angle_input = arcade.gui.UIInputText(width=220, text="0")

        # Layout widgets
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
            mass = float(self.mass_input.text)
            drag = float(self.drag_input.text)
            angle = float(self.angle_input.text)

            orbit_view = OrbitView(speed, angle, mass, drag)
            self.window.show_view(orbit_view)
        except ValueError:
            print("Please enter valid numerical values.")
#Main Exe
def main():
    window = arcade.Window(800, 600, "Satellite Simulation")
    window.show_view(MissionControlView())
    arcade.run()

if __name__ == "__main__":
    main()