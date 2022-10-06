from typing import List, Dict
import jsons
import os

class FanCurvePoint:
    def __init__(self, temp: float, speed: int):
        self.temp = temp
        self.speed = speed

    def interpolate(self, other: "FanCurvePoint", temp: float):
        if (other.temp == self.temp): # Division by zero!
            return self.speed

        return self.speed + (temp - self.temp) * (other.speed - self.speed) / (other.temp - self.temp)

class FanCurve:
    DEFAULT_LOWER_TEMP = 20
    DEFAULT_LOWER_SPEED = 10
    DEFAULT_UPPER_TEMP = 90
    DEFAULT_UPPER_SPEED = 100

    def __init__(self, points:List[FanCurvePoint]=[]):
        self.points = points

    def find_lower_point(self, temp:float):
        curr_point = None

        for point in self.points:
            if point.temp > temp:
                break
            else:
                curr_point = point

        return curr_point

    def find_upper_point(self, temp:float):
        for point in self.points:
            if point.temp >= temp:
                return point

        return None

    def get_fan_speed(self, temp:float):
        lower_point = self.find_lower_point(temp)
        upper_point = self.find_upper_point(temp)

        if lower_point == None:
            lower_point = FanCurvePoint(FanCurve.DEFAULT_LOWER_TEMP, FanCurve.DEFAULT_LOWER_SPEED)

        if upper_point == None:
            upper_point = FanCurvePoint(FanCurve.DEFAULT_UPPER_TEMP, FanCurve.DEFAULT_UPPER_SPEED)

        return min(100, max(0, lower_point.interpolate(upper_point, temp)))

class FanConfiguration:
    def __init__(self, name:str="", fan_curves:Dict[str,FanCurve]=[]):
        self.name = name
        self.fan_curves = fan_curves

    def get_CPU_fan_speed(self, temp):
        if not "cpu" in self.fan_curves:
            return 0

        return self.fan_curves["cpu"].get_fan_speed(temp)

    def get_GPU_fan_speed(self, temp):
        if not "gpu" in self.fan_curves:
            return 0

        return self.fan_curves["gpu"].get_fan_speed(temp)

    def get_fan_speed(self, cpu_temp=None, gpu_temp=None):
        cpu_speed = self.get_CPU_fan_speed(cpu_temp) if cpu_temp != None else 0
        gpu_speed = self.get_GPU_fan_speed(gpu_temp) if gpu_temp != None else 0

        return max(cpu_speed, gpu_speed)

class FanConfigurationFile:
    def __init__(self, fan_configurations:Dict[int,FanConfiguration]={}):
        self.fan_configurations = fan_configurations

    def from_json(json:str):
        dict = jsons.loads(json, Dict[int,FanConfiguration])
        return FanConfigurationFile(dict)

    def get_fan_name(self, index:int):
        if not index in self.fan_configurations:
            return "Fan " + str(index)

        return self.get_fan(index).name

    def get_fan(self, index:int):
        if not index in self.fan_configurations:
            return None

        return self.fan_configurations[index]

def load_configuration():
    try:
        file = open(os.path.join(os.getcwd(), "config.json"), 'r')
        config = FanConfigurationFile.from_json(file.read())
        file.close()
        return config
    except:
        return FanConfigurationFile()
