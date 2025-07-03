import arcade
import math

# set screen dimensions (constants)
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
SCREEN_TITLE = "Satellite Orbit Simulator"
#Earth(Constant)
EARTH_RADIUS = 100
EARTH_MASS = 5.972e24 #Will be used later
GRAVITY_CONSTANT = 1.0
#Satellite(Constant)
SATELLITE_RADIUS = 5
INITIAL_DISTANCE = 200 #From Earth center
INITIAL_SPEED = 1.6 #user-defined

#Atmospheric Factors
BASE_AIR_DENSITY = 1.2 #At Earth Surface
SCALE_HEIGHT = 10 # How fast Atmosphere thins
DRAG_COEFFICIENT = 0.00000001 #Tweakable for orbit duration

class OrbitView(arcade.View):
    def __init__(self):
        super().__init__()
        #Earth Center
        self.earth_x = SCREEN_WIDTH // 2
        self.earth_y = SCREEN_HEIGHT // 2

        #Satellite State
        self.satellite_x = self.earth_x + INITIAL_DISTANCE
        self.satellite_y = self.earth_y

        self.vx = 0
        self.vy = 0
        self.launched = False

        #Trail Buffer
        self.trail = []
        self.max_trail_length = 500
        
        #Impact and time-to
        self.impact_detected = False
        self.impact_time = None
        self.sim_time = 0 #This tracks total simulation time

        #Orbit Count
        self.total_angle_travelled = 0
        self.previous_angle = None
        self.orbit_count = 0

        #Hud State
        self.speed_text = arcade.Text("", 10, SCREEN_HEIGHT - 20, color= arcade.color.WHITE, font_size= 14)
        self.altitude_text = arcade.Text("", 10, SCREEN_HEIGHT - 40, color= arcade.color.WHITE, font_size= 14)
        self.orbit_count_text = arcade.Text("", 10, SCREEN_HEIGHT - 60, color= arcade.color.WHITE, font_size= 14)

    def on_show(self):
        arcade.set_background_color(arcade.color.BLACK)

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

    def on_update(self, delta_time):
        if not self.launched:
            return
        
        if self.impact_detected:
            return 
        
        self.sim_time += delta_time


        #Vector from Satellite to Earth center
        dx = self.earth_x - self.satellite_x
        dy = self.earth_y - self.satellite_y
        distance = math.sqrt(dx**2 + dy**2)

         #Gravitational Force (simplified)
        force = GRAVITY_CONSTANT / (distance ** 2)
        angle = math.atan2(dy, dx)
        ax = force * math.cos(angle)
        ay = force * math.sin(angle)

        if distance < EARTH_RADIUS:
            print("Impact Detected")
            self.launched = False
            self.impact_detected = True
            self.impact_time = self.sim_time
            return
        
        if self.previous_angle is not None:
            delta_angle = angle - self.previous_angle

            if delta_angle > math.pi:
                delta_angle -= 2 * math.pi
            elif delta_angle < -math.pi:
                delta_angle += 2 * math.pi

            self.total_angle_travelled += abs(delta_angle)


            if self.total_angle_travelled >= 2 * math.pi:
                self.orbit_count += 1
                self.total_angle_travelled = 0

        self.previous_angle = angle

        # Current velocity magnitude
        v = math.sqrt(self.vx**2 + self.vy**2)
        if v != 0:
            drag_magnitude = DRAG_COEFFICIENT * v**2
            drag_ax = -drag_magnitude * (self.vx / v)
            drag_ay = -drag_magnitude * (self.vy / v)
            # Add drag to acceleration
            ax += drag_ax
            ay += drag_ay

        #Update velocity
        self.vx += ax * delta_time * 20000
        self.vy += ay * delta_time * 20000
        

        #Update Position
        self.satellite_x += self.vx
        self.satellite_y += self.vy

        # --- Atmospheric drag ---

        # Estimate altitude from Earth center
        altitude = distance - EARTH_RADIUS
    
        # Air density drops exponentially with altitude
       # air_density = BASE_AIR_DENSITY * math.exp(-altitude / SCALE_HEIGHT)

        #Current position to trail
        self.trail.append((self.satellite_x, self.satellite_y))

        #Keep trial from gettting too long
        if len(self.trail) > self.max_trail_length:
            self.trail.pop(0)

        self.speed = v
        self.altitude = distance - EARTH_RADIUS

        self.speed_text.text = f"Speed: {self.speed:.2f}"
        self.altitude_text.text = f"Altitude: {self.altitude:.2f}"
        self.orbit_count_text.text = f"Orbits: {self.orbit_count}"

        
    def on_key_press(self, symbol, modifiers):
        if symbol == arcade.key.SPACE:
            if self.launched:
                return
            self.launched = True
# Vector from Earth to satellite
        dx = self.satellite_x - self.earth_x
        dy = self.satellite_y - self.earth_y
        distance = math.sqrt(dx**2 + dy**2)

        if distance == 0:
            print("Satellite is at Earth's center! Cannot launch.")
            self.launched = False
            return

        # Normalize to get radial direction
        nx = dx / distance
        ny = dy / distance

        # Rotate 90 degrees to get tangential direction
        tx = -ny
        ty = nx

        # Apply tangential initial velocity
        self.vx = INITIAL_SPEED * tx
        self.vy = INITIAL_SPEED * ty
        

#Main Exe
def main():
    window = arcade.Window(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
    view = OrbitView()
    window.show_view(view)
    arcade.run()

if __name__ == "__main__":
    main()