"""
    gridcontrol.py
    --------------
    This is the main module of Grid Control. Implements the UI and business logic.
"""

import sys
import threading

import grid
import helper
import openhwmon
import polling
import serial
import settings
import config
from PyQt5 import QtCore, QtWidgets, QtGui
from ui.mainwindow import Ui_MainWindow

# Define status icons (available in the resource file built with "pyrcc5"
ICON_RED_LED = ":/icons/led-red-on.png"
ICON_GREEN_LED = ":/icons/green-led-on.png"

class GridControl(QtWidgets.QMainWindow):
    """Create the UI, based on PyQt5.
    The UI elements are defined in "mainwindow.py" and resource file "resources_rc.py", created in QT Designer.

    To update "mainwindow.py":
        Run "pyuic5.exe --from-imports mainwindow.ui -o mainwindow.py"

    To update "resources_rc.py":
        Run "pyrcc5.exe resources.qrc -o resource_rc.py"

    Note: Never modify "mainwindow.py" or "resource_rc.py" manually.
    """

    def __init__(self):
        super().__init__()

        # Create the main window
        self.ui = Ui_MainWindow()

        # Set upp the UI
        self.ui.setupUi(self)



        # Object for locking the serial port while sending/receiving data
        self.lock = threading.Lock()

        # Serial communication object
        self.ser = serial.Serial()

        # Initialize WMI communication with OpenHardwareMonitor
        # "initialize_hwmon()" returns a WMI object
        self.hwmon = openhwmon.initialize_hwmon()

        # QSettings object for storing the UI configuration in the OS native repository (Registry for Windows, ini-file for Linux)
        # In Windows, parameters will be stored at HKEY_CURRENT_USER/SOFTWARE/GridControl/App
        self.config = config.load_configuration()

        # Get a list of available serial ports (e.g. "COM1" in Windows)
        self.serial_ports = grid.get_serial_ports()

        # Populate the "COM port" combo box with available serial ports
        self.ui.comboBoxComPorts.addItems(self.serial_ports)

        # Read saved UI configuration
        settings.read_settings(QtCore.QSettings('GridControl', 'App'), self.ui, self.hwmon)



        # Populates the tree widget on tab "Sensor Config" with values from OpenHardwareMonitor
        openhwmon.populate_tree(self.hwmon, self.ui.treeWidgetHWMonData, self.ui.checkBoxStartSilently.isChecked())

        # System tray icon
        self.trayIcon = SystemTrayIcon(QtGui.QIcon(QtGui.QPixmap(":/icons/grid.png")), self)
        self.trayIcon.show()


        # Create a QThread object that will poll the Grid for fan rpm and voltage and HWMon for temperatures
        # The lock is needed in all operations with the serial port
        self.thread = polling.PollingThread(polling_interval=int(self.ui.comboBoxPolling.currentText()),
                                            ser=self.ser,
                                            lock=self.lock,
                                            cpu_sensor_ids=self.get_cpu_sensor_ids(),
                                            gpu_sensor_ids=self.get_gpu_sensor_ids(),
                                            cpu_calc="Max" if self.ui.radioButtonCPUMax.isChecked() else "Avg",
                                            gpu_calc="Max" if self.ui.radioButtonGPUMax.isChecked() else "Avg")

        # Connect signals and slots
        self.setup_ui_logic()

        # Setup UI parameters that cannot be defined in QT Designer
        self.setup_ui_design()

        # Store current horizontal slider values
        # Used for restoring values after automatic mode has been used
        self.manual_value_fan1 = self.ui.horizontalSliderFan1.value()
        self.manual_value_fan2 = self.ui.horizontalSliderFan2.value()
        self.manual_value_fan3 = self.ui.horizontalSliderFan3.value()
        self.manual_value_fan4 = self.ui.horizontalSliderFan4.value()
        self.manual_value_fan5 = self.ui.horizontalSliderFan5.value()
        self.manual_value_fan6 = self.ui.horizontalSliderFan6.value()

        # Minimize to tray if enabled
        if self.ui.checkBoxStartMinimized.isChecked():
            self.setWindowState(QtCore.Qt.WindowMinimized)
        else:
            self.show()

        # Initialize communication
        self.init_communication()


    def setup_ui_logic(self):
        """Define QT signal and slot connections and initializes UI values."""

        # Update "Fan percentage" LCD values from horizontal sliders initial value
        self.ui.lcdNumberFan1.display(self.ui.horizontalSliderFan1.value())
        self.ui.lcdNumberFan2.display(self.ui.horizontalSliderFan2.value())
        self.ui.lcdNumberFan3.display(self.ui.horizontalSliderFan3.value())
        self.ui.lcdNumberFan4.display(self.ui.horizontalSliderFan4.value())
        self.ui.lcdNumberFan5.display(self.ui.horizontalSliderFan5.value())
        self.ui.lcdNumberFan6.display(self.ui.horizontalSliderFan6.value())

        # Update "fan labels" from "Fan Config" tab
        self.ui.groupBoxFan1.setTitle(self.config.get_fan_name(1))
        self.ui.groupBoxFan2.setTitle(self.config.get_fan_name(2))
        self.ui.groupBoxFan3.setTitle(self.config.get_fan_name(3))
        self.ui.groupBoxFan4.setTitle(self.config.get_fan_name(4))
        self.ui.groupBoxFan5.setTitle(self.config.get_fan_name(5))
        self.ui.groupBoxFan6.setTitle(self.config.get_fan_name(6))

        self.ui.groupBoxCurrentFan1.setTitle(self.config.get_fan_name(1))
        self.ui.groupBoxCurrentFan2.setTitle(self.config.get_fan_name(2))
        self.ui.groupBoxCurrentFan3.setTitle(self.config.get_fan_name(3))
        self.ui.groupBoxCurrentFan4.setTitle(self.config.get_fan_name(4))
        self.ui.groupBoxCurrentFan5.setTitle(self.config.get_fan_name(5))
        self.ui.groupBoxCurrentFan6.setTitle(self.config.get_fan_name(6))

        #  Connect events from sliders to update "Fan percentage" LCD value
        self.ui.horizontalSliderFan1.valueChanged.connect(self.ui.lcdNumberFan1.display)
        self.ui.horizontalSliderFan2.valueChanged.connect(self.ui.lcdNumberFan2.display)
        self.ui.horizontalSliderFan3.valueChanged.connect(self.ui.lcdNumberFan3.display)
        self.ui.horizontalSliderFan4.valueChanged.connect(self.ui.lcdNumberFan4.display)
        self.ui.horizontalSliderFan5.valueChanged.connect(self.ui.lcdNumberFan5.display)
        self.ui.horizontalSliderFan6.valueChanged.connect(self.ui.lcdNumberFan6.display)

        # Connect "Manual/Automatic" fan control radio button
        self.ui.radioButtonManual.toggled.connect(self.disable_enable_sliders)

        # Connect "Simulated temperatures" checkbox
        self.ui.checkBoxSimulateTemp.stateChanged.connect(self.simulate_temperatures)

        # Connect "Restart Communication" button
        self.ui.pushButtonRestart.clicked.connect(self.restart)

        # Connect "Add CPU sensors" button
        self.ui.pushButtonAddCPUSensor.clicked.connect(self.add_cpu_sensors)

        # Connect "Add GPU sensors" button
        self.ui.pushButtonAddGPUSensor.clicked.connect(self.add_gpu_sensors)

        # Connect "Remove CPU sensors" button
        self.ui.pushButtonRemoveCPUSensor.clicked.connect(self.remove_cpu_sensors)

        # Connect "Remove GPU sensors" button
        self.ui.pushButtonRemoveGPUSensor.clicked.connect(self.remove_gpu_sensors)

        # Connect event from changed serial port combo box
        self.ui.comboBoxComPorts.currentIndexChanged.connect(self.init_communication)

        # Connect event from changed polling interval combo box
        self.ui.comboBoxPolling.currentIndexChanged.connect(self.init_communication)

        # Update fan voltage (speed) based on changes to the horizontal sliders
        #
        # "grid.calculate_voltage" converts the percent value to valid voltages supported by the Grid
        # "lambda" is needed to send four arguments (serial object, fan id, fan voltage and lock object)
        self.ui.horizontalSliderFan1.valueChanged.connect(
            lambda: grid.set_fan(ser=self.ser, fan=1, voltage=grid.calculate_voltage(self.ui.lcdNumberFan1.value()) ,lock=self.lock))

        self.ui.horizontalSliderFan2.valueChanged.connect(
            lambda: grid.set_fan(ser=self.ser, fan=2, voltage=grid.calculate_voltage(self.ui.lcdNumberFan2.value()), lock=self.lock))

        self.ui.horizontalSliderFan3.valueChanged.connect(
            lambda: grid.set_fan(ser=self.ser, fan=3, voltage=grid.calculate_voltage(self.ui.lcdNumberFan3.value()), lock=self.lock))

        self.ui.horizontalSliderFan4.valueChanged.connect(
            lambda: grid.set_fan(ser=self.ser, fan=4, voltage=grid.calculate_voltage(self.ui.lcdNumberFan4.value()), lock=self.lock))

        self.ui.horizontalSliderFan5.valueChanged.connect(
            lambda: grid.set_fan(ser=self.ser, fan=5, voltage=grid.calculate_voltage(self.ui.lcdNumberFan5.value()), lock=self.lock))

        self.ui.horizontalSliderFan6.valueChanged.connect(
            lambda: grid.set_fan(ser=self.ser, fan=6, voltage=grid.calculate_voltage(self.ui.lcdNumberFan6.value()), lock=self.lock))

        # Connect fan rpm signal (from polling thread) to fan rpm label
        self.thread.rpm_signal_fan1.connect(self.ui.labelRPMFan1.setText)
        self.thread.rpm_signal_fan2.connect(self.ui.labelRPMFan2.setText)
        self.thread.rpm_signal_fan3.connect(self.ui.labelRPMFan3.setText)
        self.thread.rpm_signal_fan4.connect(self.ui.labelRPMFan4.setText)
        self.thread.rpm_signal_fan5.connect(self.ui.labelRPMFan5.setText)
        self.thread.rpm_signal_fan6.connect(self.ui.labelRPMFan6.setText)

        # Connect fan voltage signal (from polling thread) to fan voltage value
        self.thread.voltage_signal_fan1.connect(self.ui.labelVFan1.setText)
        self.thread.voltage_signal_fan2.connect(self.ui.labelVFan2.setText)
        self.thread.voltage_signal_fan3.connect(self.ui.labelVFan3.setText)
        self.thread.voltage_signal_fan4.connect(self.ui.labelVFan4.setText)
        self.thread.voltage_signal_fan5.connect(self.ui.labelVFan5.setText)
        self.thread.voltage_signal_fan6.connect(self.ui.labelVFan6.setText)

        # Connect pixmap signal (from polling thread) for updating the fan status icon
        # "lambda" is needed to transmit two arguments, "icon resource name" from the signal (x) and fan id
        self.thread.pixmap_signal_fan1.connect(lambda x: self.change_fan_icon(x, 1))
        self.thread.pixmap_signal_fan2.connect(lambda x: self.change_fan_icon(x, 2))
        self.thread.pixmap_signal_fan3.connect(lambda x: self.change_fan_icon(x, 3))
        self.thread.pixmap_signal_fan4.connect(lambda x: self.change_fan_icon(x, 4))
        self.thread.pixmap_signal_fan5.connect(lambda x: self.change_fan_icon(x, 5))
        self.thread.pixmap_signal_fan6.connect(lambda x: self.change_fan_icon(x, 6))

        # Connect CPU and GPU temperature signals (from polling thread) to GPU and CPU LCD values
        self.thread.cpu_temp_signal.connect(self.ui.lcdNumberCurrentCPU.display)
        self.thread.gpu_temp_signal.connect(self.ui.lcdNumberCurrentGPU.display)

        # Connect update signal to fan update function
        self.thread.update_signal.connect(self.update_fan_speed)

        # Connect CPU and GPU temperature signals (from polling thread) to function for updating HWMon status
        self.thread.hwmon_status_signal.connect(self.ui.labelHWMonStatus.setText)

        # Connect exception signal to show exception message from running thread
        # This is needed as it's not possible to show a message box widget from the QThread directly
        self.thread.exception_signal.connect(self.thread_exception_handling)

    def setup_ui_design(self):
        """Define UI parameters that cannot be configured in QT Creator directly."""

        # "OpenHardwareMonitor tree widget" configuration
        self.ui.treeWidgetHWMonData.setHeaderLabels(["Node", "ID", "Temp (at init)"])
        self.ui.treeWidgetHWMonData.expandAll()
        self.ui.treeWidgetHWMonData.setSortingEnabled(False)
        self.ui.treeWidgetHWMonData.sortByColumn(0, 0)
        self.ui.treeWidgetHWMonData.setColumnWidth(0, 200)
        self.ui.treeWidgetHWMonData.setColumnWidth(1, 100)
        self.ui.treeWidgetHWMonData.setColumnWidth(2, 50)
        # treeWidget.setColumnHidden(1, True)
        self.ui.treeWidgetHWMonData.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)


        # "Selected CPU sensors" tree widget configuration
        self.ui.treeWidgetSelectedCPUSensors.setHeaderLabels(["Node", "ID"])
        self.ui.treeWidgetSelectedCPUSensors.setColumnWidth(0, 150)
        self.ui.treeWidgetSelectedCPUSensors.setColumnWidth(1, 50)
        self.ui.treeWidgetSelectedCPUSensors.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)

        # "Selected GPU sensors" tree widget configuration
        self.ui.treeWidgetSelectedGPUSensors.setHeaderLabels(["Node", "ID"])
        self.ui.treeWidgetSelectedGPUSensors.setColumnWidth(0, 150)
        self.ui.treeWidgetSelectedGPUSensors.setColumnWidth(1, 50)
        self.ui.treeWidgetSelectedGPUSensors.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)

        # "Simulate temperatures" group box settings
        self.ui.checkBoxSimulateTemp.setChecked(False)
        self.ui.horizontalSliderCPUTemp.setEnabled(False)
        self.ui.horizontalSliderGPUTemp.setEnabled(False)

        # If manual mode is enabled, disable "Simulate temperatures"
        if self.ui.radioButtonManual.isChecked():
            self.ui.groupBoxSimulateTemperatures.setEnabled(False)

        # If automatic mode is enabled, disable the horizontal sliders
        if self.ui.radioButtonAutomatic.isChecked():
            self.ui.horizontalSliderFan1.setEnabled(False)
            self.ui.horizontalSliderFan2.setEnabled(False)
            self.ui.horizontalSliderFan3.setEnabled(False)
            self.ui.horizontalSliderFan4.setEnabled(False)
            self.ui.horizontalSliderFan5.setEnabled(False)
            self.ui.horizontalSliderFan6.setEnabled(False)

    def init_communication(self):
        """Configure the serial device, serial port and polling interval before starting the polling thread.

        Called at:
        - Start of application
        - When the "Serial port" or "Polling interval" combo box is changed
        - When "Restart Communication" button is clicked
        """

        # If the polling thread is running, stop it to be able to update port/polling interval and reset fans
        if self.thread.isRunning():
            self.thread.stop()

        # Reset fan and temperature data (set rpm and voltage to "---" and temp to "0")
        self.reset_data()

        # If the serial port is open, close it
        with self.lock:
            if self.ser.isOpen():
                self.ser.close()

        # Check if a serial port is selected
        if self.ui.comboBoxComPorts.currentText() != "<Select port>":
            # Setup serial device using selected serial port
            grid.setup_serial(self.ser, self.ui.comboBoxComPorts.currentText(), self.lock)

            # Open serial device
            grid.open_serial(self.ser, self.lock)

            # If manual mode is selected, enable horizontal sliders (they are disabled if no serial port is selected)
            if self.ui.radioButtonManual.isChecked():
                self.ui.horizontalSliderFan1.setEnabled(True)
                self.ui.horizontalSliderFan2.setEnabled(True)
                self.ui.horizontalSliderFan3.setEnabled(True)
                self.ui.horizontalSliderFan4.setEnabled(True)
                self.ui.horizontalSliderFan5.setEnabled(True)
                self.ui.horizontalSliderFan6.setEnabled(True)

            # Enable other UI elements
            self.ui.radioButtonManual.setEnabled(True)
            self.ui.radioButtonAutomatic.setEnabled(True)
            self.ui.checkBoxSimulateTemp.setEnabled(True)
            if self.ui.checkBoxSimulateTemp.isChecked():
                self.ui.horizontalSliderCPUTemp.setEnabled(True)
                self.ui.horizontalSliderGPUTemp.setEnabled(True)

            # Initialize the Grid+ V2 device
            if grid.initialize_grid(self.ser, self.lock):
                # Set the initial fan speeds based on UI values
                self.initialize_fans()

                # Update the polling interval (ms) based on UI value
                self.thread.update_polling_interval(new_polling_interval=int(self.ui.comboBoxPolling.currentText()))

                # Update temperature calculation (Maximum or Average) based on UI settings on "Sensor Config" tab
                self.thread.set_temp_calc(cpu_calc="Max" if self.ui.radioButtonCPUMax.isChecked() else "Avg",
                                          gpu_calc="Max" if self.ui.radioButtonGPUMax.isChecked() else "Avg")

                # Start the polling thread
                self.thread.start()

                # Update status in UI
                self.ui.labelPollingStatus.setText('<b><font color="green">Running</font></b>')

            # Handle unsuccessful initialization
            else:
                # As there is a communication problem, reset the "serial port" combo box
                index = self.ui.comboBoxComPorts.findText("<Select port>")
                self.ui.comboBoxComPorts.setCurrentIndex(index)

                # Update status in UI
                self.ui.labelPollingStatus.setText('<b><font color="red">Stopped</font></b>')

        # If no serial port is selected, disable UI elements
        else:
            self.ui.horizontalSliderFan1.setEnabled(False)
            self.ui.horizontalSliderFan2.setEnabled(False)
            self.ui.horizontalSliderFan3.setEnabled(False)
            self.ui.horizontalSliderFan4.setEnabled(False)
            self.ui.horizontalSliderFan5.setEnabled(False)
            self.ui.horizontalSliderFan6.setEnabled(False)
            self.ui.radioButtonManual.setEnabled(False)
            self.ui.radioButtonAutomatic.setEnabled(False)
            self.ui.checkBoxSimulateTemp.setEnabled(False)
            self.ui.horizontalSliderCPUTemp.setEnabled(False)
            self.ui.horizontalSliderGPUTemp.setEnabled(False)
            self.ui.horizontalSliderCPUTemp.setValue(0)
            self.ui.horizontalSliderGPUTemp.setValue(0)

    def reset_data(self):
        """Reset fan rpm and voltage to "---" and activate the red status icon.
        Reset CPU and GPU temperature to "0"."""

        # Reset fan rpm
        self.ui.labelRPMFan1.setText('<b><font color="red">---</font></b>')
        self.ui.labelRPMFan2.setText('<b><font color="red">---</font></b>')
        self.ui.labelRPMFan3.setText('<b><font color="red">---</font></b>')
        self.ui.labelRPMFan4.setText('<b><font color="red">---</font></b>')
        self.ui.labelRPMFan5.setText('<b><font color="red">---</font></b>')
        self.ui.labelRPMFan6.setText('<b><font color="red">---</font></b>')

        # Reset fan voltage
        self.ui.labelVFan1.setText('<b><font color="red">---</font></b>')
        self.ui.labelVFan2.setText('<b><font color="red">---</font></b>')
        self.ui.labelVFan3.setText('<b><font color="red">---</font></b>')
        self.ui.labelVFan4.setText('<b><font color="red">---</font></b>')
        self.ui.labelVFan5.setText('<b><font color="red">---</font></b>')
        self.ui.labelVFan6.setText('<b><font color="red">---</font></b>')

        # Activate the red led icon
        self.ui.labelStatusFan1.setPixmap(QtGui.QPixmap(ICON_RED_LED))
        self.ui.labelStatusFan2.setPixmap(QtGui.QPixmap(ICON_RED_LED))
        self.ui.labelStatusFan3.setPixmap(QtGui.QPixmap(ICON_RED_LED))
        self.ui.labelStatusFan4.setPixmap(QtGui.QPixmap(ICON_RED_LED))
        self.ui.labelStatusFan5.setPixmap(QtGui.QPixmap(ICON_RED_LED))
        self.ui.labelStatusFan6.setPixmap(QtGui.QPixmap(ICON_RED_LED))

        # Reset temperatures
        self.ui.lcdNumberCurrentCPU.display(0)
        self.ui.lcdNumberCurrentGPU.display(0)

        # Update status in UI
        self.ui.labelPollingStatus.setText('<b><font color="red">Stopped</font></b>')
        self.ui.labelHWMonStatus.setText('<b><font color="red">---</font></b>')

    def initialize_fans(self):
        """Initialize fans to the initial slider values."""

        grid.set_fan(ser=self.ser, fan=1, voltage=grid.calculate_voltage(self.ui.lcdNumberFan1.value()), lock=self.lock)
        grid.set_fan(ser=self.ser, fan=2, voltage=grid.calculate_voltage(self.ui.lcdNumberFan2.value()), lock=self.lock)
        grid.set_fan(ser=self.ser, fan=3, voltage=grid.calculate_voltage(self.ui.lcdNumberFan3.value()), lock=self.lock)
        grid.set_fan(ser=self.ser, fan=4, voltage=grid.calculate_voltage(self.ui.lcdNumberFan4.value()), lock=self.lock)
        grid.set_fan(ser=self.ser, fan=5, voltage=grid.calculate_voltage(self.ui.lcdNumberFan5.value()), lock=self.lock)
        grid.set_fan(ser=self.ser, fan=6, voltage=grid.calculate_voltage(self.ui.lcdNumberFan6.value()), lock=self.lock)

    def disable_enable_sliders(self):
        """Disables the horizontal sliders if "Automatic" mode is selected.
        When changing from automatic to manual mode, restore manual values."""

        # If "Automatic" radio button was clicked (i.e. it's "Checked")
        if self.ui.radioButtonAutomatic.isChecked():
            # Save current manual values
            self.manual_value_fan1 = self.ui.horizontalSliderFan1.value()
            self.manual_value_fan2 = self.ui.horizontalSliderFan2.value()
            self.manual_value_fan3 = self.ui.horizontalSliderFan3.value()
            self.manual_value_fan4 = self.ui.horizontalSliderFan4.value()
            self.manual_value_fan5 = self.ui.horizontalSliderFan5.value()
            self.manual_value_fan6 = self.ui.horizontalSliderFan6.value()

            # Disable sliders
            self.ui.horizontalSliderFan1.setEnabled(False)
            self.ui.horizontalSliderFan2.setEnabled(False)
            self.ui.horizontalSliderFan3.setEnabled(False)
            self.ui.horizontalSliderFan4.setEnabled(False)
            self.ui.horizontalSliderFan5.setEnabled(False)
            self.ui.horizontalSliderFan6.setEnabled(False)

            # Enable simulate temperatures
            self.ui.groupBoxSimulateTemperatures.setEnabled(True)

        # If "Manual" radio button was clicked
        else:
            # Restore saved manual values
            self.ui.horizontalSliderFan1.setValue(self.manual_value_fan1)
            self.ui.horizontalSliderFan2.setValue(self.manual_value_fan2)
            self.ui.horizontalSliderFan3.setValue(self.manual_value_fan3)
            self.ui.horizontalSliderFan4.setValue(self.manual_value_fan4)
            self.ui.horizontalSliderFan5.setValue(self.manual_value_fan5)
            self.ui.horizontalSliderFan6.setValue(self.manual_value_fan6)

            # Enable sliders
            self.ui.horizontalSliderFan1.setEnabled(True)
            self.ui.horizontalSliderFan2.setEnabled(True)
            self.ui.horizontalSliderFan3.setEnabled(True)
            self.ui.horizontalSliderFan4.setEnabled(True)
            self.ui.horizontalSliderFan5.setEnabled(True)
            self.ui.horizontalSliderFan6.setEnabled(True)

            # Disable simulate temperatures
            self.ui.groupBoxSimulateTemperatures.setEnabled(False)
            self.ui.checkBoxSimulateTemp.setChecked(False)

    def update_fan_speed(self):
        """Update fan speed based on CPU and GPU temperatures."""

        # If automatic mode is selected
        if self.ui.radioButtonAutomatic.isChecked():
            # For each fan (1 ... 6)
            for i in range(1, 7):
                fan = self.config.get_fan(i)

                if fan == None:
                    continue

                fan_speed = fan.get_fan_speed(
                        cpu_temp=self.ui.lcdNumberCurrentCPU.value(),
                        gpu_temp=self.ui.lcdNumberCurrentGPU.value()
                )

                # Update horizontal slider value
                getattr(self.ui, "horizontalSliderFan" + str(i)).setValue(round(fan_speed))

    def simulate_temperatures(self):
        """Simulate CPU and GPU temperatures, used for verifying the functionality of the fan control system."""

        # If "Simulate temperatures" checkbox is enabled
        if self.ui.checkBoxSimulateTemp.isChecked():
            # Enable sliders
            self.ui.horizontalSliderCPUTemp.setEnabled(True)
            self.ui.horizontalSliderGPUTemp.setEnabled(True)

            # Update CPU and GPU values from current horizontal slider values
            self.ui.lcdNumberCurrentCPU.display(self.ui.horizontalSliderCPUTemp.value())
            self.ui.lcdNumberCurrentGPU.display(self.ui.horizontalSliderGPUTemp.value())

            # Disconnect temperature signals from polling thread
            self.thread.cpu_temp_signal.disconnect(self.ui.lcdNumberCurrentCPU.display)
            self.thread.gpu_temp_signal.disconnect(self.ui.lcdNumberCurrentGPU.display)

            # Connect the horizontal sliders to the "CPU" and "GPU" LCD widget
            self.ui.horizontalSliderCPUTemp.valueChanged.connect(self.ui.lcdNumberCurrentCPU.display)
            self.ui.horizontalSliderGPUTemp.valueChanged.connect(self.ui.lcdNumberCurrentGPU.display)

            # Update group box headers to indicate simulation mode
            self.ui.groupBoxCurrentCPUTemp.setTitle("Sim. CPU temp")
            self.ui.groupBoxCurrentGPUTemp.setTitle("Sim. GPU temp")

        # If "Simulate temperatures" checkbox is disabled, reset settings
        else:
            # Disable horizontal sliders
            self.ui.horizontalSliderCPUTemp.setEnabled(False)
            self.ui.horizontalSliderGPUTemp.setEnabled(False)

            # Reconnect signals from polling thread
            self.thread.cpu_temp_signal.connect(self.ui.lcdNumberCurrentCPU.display)
            self.thread.gpu_temp_signal.connect(self.ui.lcdNumberCurrentGPU.display)

            # Reset headers in UI
            self.ui.groupBoxCurrentCPUTemp.setTitle("Current CPU temp")
            self.ui.groupBoxCurrentGPUTemp.setTitle("Current GPU temp")

    def restart(self):
        """Update 'Selected CPU and GPU sensors' and restart application"""

        # TODO: Add apply button
        self.thread.update_sensors(self.get_cpu_sensor_ids(), self.get_gpu_sensor_ids())
        self.init_communication()

    def thread_exception_handling(self, msg):
        """Display an error message with details about the exception and reset the "serial port value" to <Select port>.
        Called when an exception occurs in the polling thread."""

        # Show error message
        helper.show_error(msg)

        # Reset the "serial port" combo box
        index = self.ui.comboBoxComPorts.findText("<Select port>")
        self.ui.comboBoxComPorts.setCurrentIndex(index)

    def add_cpu_sensors(self):
        """Add selected temperature sensor(s) to the "Selected CPU sensor(s)" three widget."""

        items = [item for item in self.ui.treeWidgetHWMonData.selectedItems()]

        # The new items should have the tree widget itself as parent
        parent = self.ui.treeWidgetSelectedCPUSensors

        for item in items:
            sensor_item = QtWidgets.QTreeWidgetItem(parent)
            sensor_item.setText(0, item.text(0))
            sensor_item.setText(1, item.text(1))
            sensor_item.setForeground(0, QtGui.QBrush(QtCore.Qt.blue))  # Text color blue

        # Deselect all items in the HWMon tree widget after they have been added
        self.ui.treeWidgetHWMonData.clearSelection()

    def add_gpu_sensors(self):
        """Add selected temperature sensor(s) to the "Selected GPU sensor(s)" three widget."""
        items = [item for item in self.ui.treeWidgetHWMonData.selectedItems()]

        # The new items should have the tree widget itself as parent
        parent = self.ui.treeWidgetSelectedGPUSensors

        for item in items:
            sensor_item = QtWidgets.QTreeWidgetItem(parent)
            sensor_item.setText(0, item.text(0))
            sensor_item.setText(1, item.text(1))
            sensor_item.setForeground(0, QtGui.QBrush(QtCore.Qt.blue))  # Text color blue

        # Deselect all items in the HWMon tree widget after they have been added
        self.ui.treeWidgetHWMonData.clearSelection()

    def remove_cpu_sensors(self):
        """Remove selected CPU sensors."""

        root = self.ui.treeWidgetSelectedCPUSensors.invisibleRootItem()
        for item in self.ui.treeWidgetSelectedCPUSensors.selectedItems():
            root.removeChild(item)

    def remove_gpu_sensors(self):
        """Remove selected GPU sensors."""

        root = self.ui.treeWidgetSelectedGPUSensors.invisibleRootItem()
        for item in self.ui.treeWidgetSelectedGPUSensors.selectedItems():
            root.removeChild(item)

    def get_cpu_sensor_ids(self):
        """Get id's for each sensor in the "Selected CPU sensors" tree."""

        root = self.ui.treeWidgetSelectedCPUSensors.invisibleRootItem()
        child_count = root.childCount()
        cpu_sensor_ids = []
        for i in range(child_count):
            item = root.child(i)
            cpu_sensor_ids.append(item.text(1))  # Second column is the id
        return cpu_sensor_ids

    def get_gpu_sensor_ids(self):
        """Get id's for each sensor in the "Selected GPU sensors" tree."""

        root = self.ui.treeWidgetSelectedGPUSensors.invisibleRootItem()
        child_count = root.childCount()
        gpu_sensor_ids = []
        for i in range(child_count):
            item = root.child(i)
            gpu_sensor_ids.append(item.text(1))  # Second column is the id
        return gpu_sensor_ids

    def change_fan_icon(self, icon, fan):
        """Update the fan status icon."""

        if fan == 1:
            self.ui.labelStatusFan1.setPixmap(QtGui.QPixmap(icon))
        if fan == 2:
            self.ui.labelStatusFan2.setPixmap(QtGui.QPixmap(icon))
        if fan == 3:
            self.ui.labelStatusFan3.setPixmap(QtGui.QPixmap(icon))
        if fan == 4:
            self.ui.labelStatusFan4.setPixmap(QtGui.QPixmap(icon))
        if fan == 5:
            self.ui.labelStatusFan5.setPixmap(QtGui.QPixmap(icon))
        if fan == 6:
            self.ui.labelStatusFan6.setPixmap(QtGui.QPixmap(icon))

    def closeEvent(self, event):
        """Save UI settings and stops the running thread gracefully, then exit the application.
        Called when closing the application window.
        """

        # Stop the running thread
        if self.thread.isRunning():
            self.thread.stop()
            print("Thread stopped")

        # Hide tray icon
        self.trayIcon.hide()

        # Accept the closing event and close application
        event.accept()

    def changeEvent(self, event):
        if event.type() == QtCore.QEvent.WindowStateChange:
            if self.windowState() & QtCore.Qt.WindowMinimized:
                if self.ui.checkBoxMinimizeToTray.isChecked():
                    event.ignore()
                    self.minimize_to_tray()
                else:
                    self.show()
                    event.accept()

    def toggle_visibility(self):
        if self.isVisible():
            self.minimize_to_tray()
        else:
            self.restore_from_tray()

    def minimize_to_tray(self):
        self.hide()
        # self.trayIcon.show()

    def restore_from_tray(self):
        self.setWindowState(self.windowState() & ~QtCore.Qt.WindowMinimized | QtCore.Qt.WindowActive)
        self.activateWindow()
        self.show()
        # self.trayIcon.hide()


class SystemTrayIcon(QtWidgets.QSystemTrayIcon):

    def __init__(self, icon, parent=None):
        super(SystemTrayIcon, self).__init__(icon, parent)
        self.parent = parent
        self.setToolTip("Grid Control")
        self.activated.connect(self.on_systemTrayIcon_activated)
        menu = QtWidgets.QMenu()
        showAction = menu.addAction("Hide/Show")
        showAction.triggered.connect(parent.toggle_visibility)
        menu.addSeparator()
        exitAction = menu.addAction("Exit")
        exitAction.triggered.connect(parent.close)
        self.setContextMenu(menu)

    def on_systemTrayIcon_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.DoubleClick:
            self.parent.toggle_visibility()


if __name__ == "__main__":
    # Use a rewritten excepthook for displaying unhandled exceptions as a QMessageBox
    sys.excepthook = helper.excepthook

    # Create the QT application
    app = QtWidgets.QApplication(sys.argv)

    # Create the main window
    win = GridControl()

    # Set program version
    win.setWindowTitle("Grid Control 1.0.9")

    # Show window
    #win.show()

    # Disable window resizing
    win.setFixedSize(win.size())

    # Start QT application
    sys.exit(app.exec_())
