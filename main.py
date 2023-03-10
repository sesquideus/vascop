#!/usr/bin/env python

import sys
import yaml
import dotmap
import datetime
import functools
import zoneinfo
import numpy as np

from astropy import units as u
from astropy.coordinates import EarthLocation

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget

import matplotlib as mpl
from matplotlib import pyplot as plt

from matchers import Matchmaker, Counselor
from projections import BorovickaProjection
from photometry import Calibration, LogCalibration

from plots import SensorPlot
from plots.sky import PositionSkyPlot, MagnitudeSkyPlot
from plots.errors import PositionErrorPlot, MagnitudeErrorPlot
from plots.correction import BaseCorrectionPlot, PositionCorrectionPlot, MagnitudeCorrectionPlot
from utilities import unit_grid

from main_ui import Ui_MainWindow

from amos import AMOS, Station

mpl.use('Qt5Agg')

COUNT = 100


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.position_errors = None
        self.magnitude_errors = None
        self.location = None
        self.time = None
        self.projection = None
        self.calibration = None
        self.matcher = None

        self.setupUi(self)
        self.param_widgets = [
            (self.dsb_x0, 'x0'), (self.dsb_y0, 'y0'), (self.dsb_a0, 'a0'), (self.dsb_A, 'A'), (self.dsb_F, 'F'),
            (self.dsb_V, 'V'), (self.dsb_S, 'S'), (self.dsb_D, 'D'), (self.dsb_P, 'P'), (self.dsb_Q, 'Q'),
            (self.dsb_eps, 'eps'), (self.dsb_E, 'E')
        ]

        self.settings = dotmap.DotMap(dict(
            resolution=dict(left=-1, bottom=-1, right=1, top=1)
        ))

        self.populateStations()

        plt.style.use('dark_background')
        self.sensorPlot = SensorPlot(self.tab_sensor)
        self.positionSkyPlot = PositionSkyPlot(self.tab_sky_positions)
        self.magnitudeSkyPlot = MagnitudeSkyPlot(self.tab_sky_magnitudes)
        self.positionErrorPlot = PositionErrorPlot(self.tab_errors_positions)
        self.magnitudeErrorPlot = MagnitudeErrorPlot(self.tab_errors_magnitudes)
        self.positionCorrectionPlot = PositionCorrectionPlot(self.tab_correction_positions_enabled)
        self.magnitudeCorrectionPlot = MagnitudeCorrectionPlot(self.tab_correction_magnitudes_enabled)

        self.calibration = LogCalibration(4000)

        self.updateProjection()

        self.loadYAML('data/M20120922_225744_AGO__00007.yaml')  # temporary
        self.importConstants('AGO.yaml')  # temporary

        self.onParametersChanged()
        self.connectSignalSlots()

    def populateStations(self):
        for name, station in AMOS.stations.items():
            self.cb_stations.addItem(station.name)

        self.cb_stations.currentIndexChanged.connect(self.selectStation)

    def selectStation(self, index):
        if index == 0:
            station = Station("custom", self.dsb_lat.value(), self.dsb_lon.value(), 0)
        else:
            station = list(AMOS.stations.values())[index - 1]

        self.dsb_lat.setValue(station.latitude)
        self.dsb_lon.setValue(station.longitude)

        self.updateMatcher()
        self.onLocationTimeChanged()

    def connectSignalSlots(self):
        self.ac_load.triggered.connect(self.loadYAMLFile)

        for widget, param in self.param_widgets:
            widget.valueChanged.connect(self.onParametersChanged)

        self.dt_time.dateTimeChanged.connect(self.updateTime)
        self.dt_time.dateTimeChanged.connect(self.onTimeChanged)

        self.dsb_lat.valueChanged.connect(self.onLocationChanged)
        self.dsb_lon.valueChanged.connect(self.onLocationChanged)

        self.pb_optimize.clicked.connect(self.minimize)
        self.pb_pair.clicked.connect(self.pair)
        self.pb_export.clicked.connect(self.exportFile)
        self.pb_import.clicked.connect(self.importFile)

        self.pb_mask_unidentified.clicked.connect(self.maskSensor)
        self.pb_mask_distant.clicked.connect(self.maskCatalogueDistant)
        self.pb_mask_faint.clicked.connect(self.maskCatalogueFaint)
        self.pb_reset.clicked.connect(self.resetValid)
        self.dsb_error_limit.valueChanged.connect(self.onErrorLimitChanged)

        self.dsb_bandwidth.valueChanged.connect(self.onBandwidthChanged)
        self.sb_arrow_scale.valueChanged.connect(self.onArrowScaleChanged)
        self.sb_resolution.valueChanged.connect(self.onResolutionChanged)

        self.cb_show_errors.clicked.connect(self.plotPositionCorrectionErrors)
        self.cb_show_grid.clicked.connect(self.plotPositionCorrectionGrid)

        self.tw_charts.currentChanged.connect(self.updatePlots)

    def onTimeChanged(self):
        self.updateTime()
        self.onLocationTimeChanged()

    def onLocationChanged(self):
        self.updateLocation()
        self.onLocationTimeChanged()

    def setLocation(self, lat, lon):
        self.dsb_lat.setValue(lat)
        self.dsb_lon.setValue(lon)

    def updateLocation(self):
        self.location = EarthLocation(self.dsb_lon.value() * u.deg, self.dsb_lat.value() * u.deg)

    def setTime(self, time):
        self.dt_time.setDateTime(time)

    def updateTime(self):
        self.time = self.dt_time.dateTime().toString('yyyy-MM-dd HH:mm:ss')

    def updateMatcher(self):
        self.matcher.update(self.location, self.time)
        self.matcher.update_position_smoother(self.projection)

    def updateProjection(self):
        self.projection = BorovickaProjection(*self.getConstantsTuple())

    def onParametersChanged(self):
        print("Parameters changed")
        self.updateProjection()

        self.positionSkyPlot.invalidate_dots()
        self.positionSkyPlot.invalidate_meteor()
        self.magnitudeSkyPlot.invalidate_dots()
        self.magnitudeSkyPlot.invalidate_meteor()
        self.positionErrorPlot.invalidate()
        self.magnitudeErrorPlot.invalidate()
        self.positionCorrectionPlot.invalidate()
        self.magnitudeCorrectionPlot.invalidate()
        self.matcher.update_position_smoother(self.projection, bandwidth=self.dsb_bandwidth.value())

        self.computePositionErrors()
        self.computeMagnitudeErrors()
        self.updatePlots()

    def onLocationTimeChanged(self):
        self.updateMatcher()
        self.positionSkyPlot.invalidate_stars()
        self.magnitudeSkyPlot.invalidate_stars()
        self.positionErrorPlot.invalidate()
        self.magnitudeErrorPlot.invalidate()
        self.matcher.update_position_smoother(self.projection, bandwidth=self.dsb_bandwidth.value())
        self.matcher.update_magnitude_smoother(self.projection, self.calibration, bandwidth=self.dsb_bandwidth.value())
        self.positionCorrectionPlot.invalidate()
        self.magnitudeCorrectionPlot.invalidate()

        self.computePositionErrors()
        self.computeMagnitudeErrors()
        self.updatePlots()

    def onErrorLimitChanged(self):
        self.positionSkyPlot.invalidate_dots()
        self.positionErrorPlot.invalidate()
        self.positionCorrectionPlot.invalidate_dots()
        self.updatePlots()

    def onBandwidthChanged(self):
        self.matcher.update_position_smoother(self.projection, bandwidth=self.dsb_bandwidth.value())
        self.matcher.update_magnitude_smoother(self.projection, self.calibration, bandwidth=self.dsb_bandwidth.value())
        self.positionCorrectionPlot.invalidate_grid()
        self.positionCorrectionPlot.invalidate_meteor()
        self.magnitudeCorrectionPlot.invalidate_grid()
        self.magnitudeCorrectionPlot.invalidate_meteor()
        self.updatePlots()

    def onArrowScaleChanged(self):
        self.positionCorrectionPlot.invalidate_dots()
        self.positionCorrectionPlot.invalidate_meteor()
        self.updatePlots()

    def onResolutionChanged(self):
        self.positionCorrectionPlot.invalidate_grid()
        self.magnitudeCorrectionPlot.invalidate_grid()
        self.updatePlots()

    def updatePlots(self):
        self.showErrors()
        self.correctMeteor()
        index = self.tw_charts.currentIndex()

        if index == 0:
            if not self.sensorPlot.valid:
                self.plotSensorData()
        elif index == 1:
            if not self.positionSkyPlot.valid_dots:
                self.plotObservedStarsPositions()
            if not self.positionSkyPlot.valid_stars:
                self.plotCatalogueStarsPositions()
        elif index == 2:
            if not self.magnitudeSkyPlot.valid_dots:
                self.plotObservedStarsMagnitudes()
            if not self.magnitudeSkyPlot.valid_stars:
                self.plotCatalogueStarsMagnitudes()
        elif index == 3:
            if not self.positionErrorPlot.valid:
                self.plotPositionErrors()
        elif index == 4:
            if not self.positionErrorPlot.valid:
                self.plotMagnitudeErrors()
        elif index == 5:
            if not self.positionCorrectionPlot.valid_dots:
                self.plotPositionCorrectionErrors()
            if not self.positionCorrectionPlot.valid_meteor:
                self.plotPositionCorrectionMeteor()
            if not self.positionCorrectionPlot.valid_grid:
                self.plotPositionCorrectionGrid()
        elif index == 6:
            if not self.magnitudeCorrectionPlot.valid_dots:
                self.plotMagnitudeCorrectionErrors()
            if not self.magnitudeCorrectionPlot.valid_meteor:
                self.plotMagnitudeCorrectionMeteor()
            if not self.magnitudeCorrectionPlot.valid_grid:
                self.plotMagnitudeCorrectionGrid()

    def computePositionErrors(self):
        self.position_errors = self.matcher.position_errors(self.projection, masked=True)

    def computeMagnitudeErrors(self):
        self.magnitude_errors = self.matcher.magnitude_errors(self.projection, self.calibration, masked=True)

    def exportFile(self):
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export constants to file", ".",
                                                            "YAML files (*.yaml)")
        if filename is not None:
            self.exportConstants(filename)

    def exportConstants(self, filename):
        try:
            with open(filename, 'w+') as file:
                yaml.dump(dict(
                    proj='Borovicka',
                    params=dict(
                        x0=self.dsb_x0.value(),
                        y0=self.dsb_y0.value(),
                        a0=self.dsb_a0.value(),
                        A=self.dsb_A.value(),
                        F=self.dsb_F.value(),
                        V=self.dsb_V.value(),
                        S=self.dsb_S.value(),
                        D=self.dsb_D.value(),
                        P=self.dsb_P.value(),
                        Q=self.dsb_Q.value(),
                        eps=self.dsb_eps.value(),
                        E=self.dsb_E.value(),
                    )
                ), file)
        except FileNotFoundError as exc:
            print(f"Could not export constants: {exc}")

    def loadYAMLFile(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load Kvant YAML file", "data",
                                                            "YAML files (*.yml *.yaml)")
        if filename == '':
            print("No file provided, loading aborted")
        else:
            self.loadYAML(filename)

        self.cb_stations.setCurrentIndex(0)
        self.onLocationTimeChanged()
        self.onParametersChanged()
        self.sensorPlot.invalidate()
        self.updatePlots()

    def loadYAML(self, file):
        data = dotmap.DotMap(yaml.safe_load(open(file, 'r')))
        self.setLocation(data.Latitude, data.Longitude)
        self.updateLocation()
        self.setTime(datetime.datetime
                     .strptime(data.EventStartTime, "%Y-%m-%d %H:%M:%S.%f")
                     .replace(tzinfo=zoneinfo.ZoneInfo('UTC')))
        self.updateTime()

        self.matcher = Matchmaker(self.location, self.time)
        self.matcher.sensor_data.load(data)
        self.matcher.load_catalogue('catalogue/HYG30.tsv')

    def importFile(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import constants from file", ".",
                                                            "YAML files (*.yml *.yaml)")
        self.importConstants(filename)
        self.onParametersChanged()

    def importConstants(self, filename):
        try:
            with open(filename, 'r') as file:
                try:
                    data = dotmap.DotMap(yaml.safe_load(file))
                    self.blockParameterSignals(True)
                    for widget, param in self.param_widgets:
                        widget.setValue(data.params[param])
                    self.blockParameterSignals(False)

                    self.updateProjection()
                except yaml.YAMLError as exc:
                    print(f"Could not open file {filename}: {exc}")
        except FileNotFoundError as exc:
            print(f"Could not import constants: {exc}")

    def blockParameterSignals(self, block):
        for widget, param in self.param_widgets:
            widget.blockSignals(block)

    def getConstantsTuple(self):
        return (
            self.dsb_x0.value(),
            self.dsb_y0.value(),
            np.radians(self.dsb_a0.value()),
            self.dsb_A.value(),
            np.radians(self.dsb_F.value()),
            self.dsb_V.value(),
            self.dsb_S.value(),
            self.dsb_D.value(),
            self.dsb_P.value(),
            self.dsb_Q.value(),
            np.radians(self.dsb_eps.value()),
            np.radians(self.dsb_E.value()),
        )

    def minimize(self):
        self.w_input.setEnabled(False)
        self.w_input.repaint()

        result = self.matcher.minimize(
            #    location=self.location,
            #    time=self.time,
            x0=self.getConstantsTuple(),
            maxiter=self.sb_maxiter.value()
        )

        x0, y0, a0, A, F, V, S, D, P, Q, e, E = tuple(result.x)
        self.blockParameterSignals(True)
        self.dsb_x0.setValue(x0)
        self.dsb_y0.setValue(y0)
        self.dsb_a0.setValue(np.degrees(a0))
        self.dsb_A.setValue(A)
        self.dsb_F.setValue(np.degrees(F))
        self.dsb_V.setValue(V)
        self.dsb_S.setValue(S)
        self.dsb_D.setValue(D)
        self.dsb_P.setValue(P)
        self.dsb_Q.setValue(Q)
        self.dsb_eps.setValue(np.degrees(e))
        self.dsb_E.setValue(np.degrees(E))
        self.blockParameterSignals(False)

        self.w_input.setEnabled(True)
        self.w_input.repaint()
        self.onParametersChanged()

    def maskSensor(self):
        errors = self.matcher.position_errors(self.projection, masked=False)
        self.matcher.mask_sensor_data(errors > np.radians(self.dsb_error_limit.value()))
        print(f"Culled the dots to {self.dsb_error_limit.value()}°: "
              f"{self.matcher.sensor_data.stars.count_valid} are valid")
        self.onParametersChanged()
        self.showCounts()

    def maskCatalogueDistant(self):
        errors = self.matcher.errors_inverse(self.projection, masked=False)
        self.matcher.mask_catalogue(errors > np.radians(self.dsb_distance_limit.value()))
        print(f"Culled the catalogue to {self.dsb_distance_limit.value()}°: "
              f"{self.matcher.catalogue.count_valid} stars used")
        self.positionSkyPlot.invalidate_stars()

        self.computePositionErrors()
        self.computeMagnitudeErrors()
        self.updatePlots()
        self.showCounts()

    def maskCatalogueFaint(self):
        self.matcher.mask_catalogue(self.matcher.catalogue.vmag > self.dsb_magnitude_limit.value())
        print(f"Culled the catalogue to {self.dsb_magnitude_limit.value()}m: "
              f"{self.matcher.catalogue.count_valid} stars used")
        self.positionSkyPlot.invalidate_stars()

        self.computePositionErrors()
        self.computeMagnitudeErrors()
        self.updatePlots()
        self.showCounts()

    def resetValid(self):
        self.matcher.reset_mask()
        self.onParametersChanged()
        self.showCounts()

    @property
    def paired(self) -> bool:
        return isinstance(self.matcher, Counselor)

    @QtCore.pyqtSlot()
    def showCounts(self) -> None:
        if isinstance(self.matcher, Counselor):
            self.lb_mode.setText("paired")
            self.tab_correction_magnitudes_enabled.setEnabled(True)
        else:
            self.lb_mode.setText("unpaired")
            self.tab_correction_magnitudes_enabled.setEnabled(False)

        self.lb_catalogue_all.setText(f'{self.matcher.catalogue.count}')
        self.lb_catalogue_near.setText(f'{self.matcher.catalogue.count_valid}')
        self.lb_objects_all.setText(f'{self.matcher.sensor_data.stars.count}')
        self.lb_objects_near.setText(f'{self.matcher.sensor_data.stars.count_valid}')

    def showErrors(self) -> None:
        avg_error = self.matcher.avg_error(self.position_errors)
        max_error = self.matcher.max_error(self.position_errors)
        self.lb_avg_error.setText(f'{np.degrees(avg_error):.6f}°')
        self.lb_max_error.setText(f'{np.degrees(max_error):.6f}°')
        self.lb_total_stars.setText(f'{self.matcher.catalogue.count}')
        outside_limit = self.position_errors[self.position_errors > np.radians(self.dsb_error_limit.value())].size
        self.lb_outside_limit.setText(f'{outside_limit}')

    def correctMeteor(self):
        if self.paired:
            self.matcher.print_meteor(self.projection)

    def plotSensorData(self):
        self.sensorPlot.update(self.matcher.sensor_data)

    def _plotObservedStars(self, plot, errors, *, limit=None):
        plot.update_dots(
            self.matcher.sensor_data.stars.project(self.projection, masked=True),
            self.matcher.sensor_data.stars.i,
            errors,
            limit=limit,
        )
        plot.update_meteor(
            self.matcher.sensor_data.meteor.project(self.projection, masked=True),
            self.matcher.sensor_data.meteor.i
        )

    def plotObservedStarsPositions(self):
        self._plotObservedStars(self.positionSkyPlot, self.position_errors,
                                limit=np.radians(self.dsb_error_limit.value()))

    def plotObservedStarsMagnitudes(self):
        self._plotObservedStars(self.magnitudeSkyPlot, self.magnitude_errors,
                                limit=np.radians(self.dsb_error_limit.value()))

    def _plotCatalogueStars(self, plot):
        plot.update_stars(
            self.matcher.catalogue.to_altaz_chart(self.location, self.time, masked=True),
            self.matcher.catalogue.vmag(masked=True)
        )

    def plotCatalogueStarsPositions(self):
        self._plotCatalogueStars(self.positionSkyPlot)

    def plotCatalogueStarsMagnitudes(self):
        self._plotCatalogueStars(self.magnitudeSkyPlot)

    def _plotErrors(self, plot, errors):
        positions = self.matcher.sensor_data.stars.project(self.projection, masked=True)
        magnitudes = self.matcher.sensor_data.stars.intensities(True)
        plot.update(positions, magnitudes, errors, limit=np.radians(self.dsb_error_limit.value()))

    def plotPositionErrors(self):
        self._plotErrors(self.positionErrorPlot, self.position_errors)

    def plotMagnitudeErrors(self):
        self._plotErrors(self.magnitudeErrorPlot, self.magnitude_errors)

    """ Methods for updating correction plots """

    def _plotCorrectionErrors(self, tabs: QStackedWidget, plot: BaseCorrectionPlot, *, intent: str) -> None:
        # Do nothing if working in unpaired mode
        if self.paired:
            tabs.setCurrentIndex(1)
            if self.cb_show_errors.isChecked():
                print(f"Plotting correction errors for {intent}")
                plot.update_dots(
                    self.matcher.catalogue.altaz(self.location, self.time, masked=True),
                    self.matcher.sensor_data.stars.project(self.projection, masked=True),
                    self.matcher.catalogue.vmag(masked=True),
                    self.matcher.sensor_data.stars.calibrate(self.calibration, masked=True),
                    limit=np.radians(self.dsb_error_limit.value()),
                    scale=1 / self.sb_arrow_scale.value(),
                )
            else:
                plot.clear_errors()
        else:
            tabs.setCurrentIndex(0)

    def plotPositionCorrectionErrors(self):
        self._plotCorrectionErrors(self.tabs_positions, self.positionCorrectionPlot, intent="star positions")

    def plotMagnitudeCorrectionErrors(self):
        self._plotCorrectionErrors(self.tabs_magnitudes, self.magnitudeCorrectionPlot, intent="star magnitudes")

    def _plotCorrectionMeteor(self, tabs, plot, *, intent: str) -> None:
        if self.paired:
            print(f"Plotting correction for {intent}")
            tabs.setCurrentIndex(1)
            plot.update_meteor(
                self.matcher.sensor_data.meteor.project(self.projection, masked=True),
                self.matcher.correction_meteor_xy(self.projection),
                self.matcher.sensor_data.meteor.calibrate(self.calibration, masked=True),
                self.matcher.correction_meteor_mag(self.projection),
                scale=1 / self.sb_arrow_scale.value(),
            )
        else:
            tabs.setCurrentIndex(0)

    def plotPositionCorrectionMeteor(self) -> None:
        self._plotCorrectionMeteor(self.tabs_positions, self.positionCorrectionPlot, intent="star positions")

    def plotMagnitudeCorrectionMeteor(self) -> None:
        self._plotCorrectionMeteor(self.tabs_magnitudes, self.magnitudeCorrectionPlot, intent="star magnitudes")

    def switch_tabs(self, tabs, func, arg, *, message: str, intent: str) -> None:
        if self.paired:
            tabs.setCurrentIndex(1)
            print(f"{message} for {intent}")
            func(arg)
        else:
            tabs.setCurrentIndex(0)

    def _plotCorrectionGrid(self, plot, grid, *, masked: bool):
        if self.cb_show_grid.isChecked():
            xx, yy = unit_grid(self.sb_resolution.value(), masked=masked)
            plot.update_grid(xx, yy, grid(resolution=self.sb_resolution.value()))
        else:
            plot.clear_grid()

    def plotPositionCorrectionGrid(self):
        self.switch_tabs(
            self.tabs_positions,
            lambda x: self._plotCorrectionGrid(x, self.matcher.position_grid, masked=True),
            self.positionCorrectionPlot,
            message="Plotting correction grid",
            intent="star positions",
        )

    def plotMagnitudeCorrectionGrid(self):
        self.switch_tabs(
            self.tabs_magnitudes,
            lambda x: self._plotCorrectionGrid(x, self.matcher.magnitude_grid, masked=False),
            self.magnitudeCorrectionPlot,
            message="Plotting correction grid",
            intent="star magnitudes",
        )

    def pair(self):
        self.matcher = self.matcher.pair(self.projection)
        self.matcher.update_position_smoother(self.projection, bandwidth=self.dsb_bandwidth.value())
        self.matcher.update_magnitude_smoother(self.projection, self.calibration, bandwidth=self.dsb_bandwidth.value())

        self.positionSkyPlot.invalidate_dots()
        self.positionSkyPlot.invalidate_stars()
        self.magnitudeSkyPlot.invalidate_dots()
        self.magnitudeSkyPlot.invalidate_stars()
        self.positionErrorPlot.invalidate()
        self.magnitudeErrorPlot.invalidate()
        self.positionCorrectionPlot.invalidate()
        self.magnitudeCorrectionPlot.invalidate()
        self.showCounts()
        self.updatePlots()


app = QApplication(sys.argv)
window = MainWindow()
window.showMaximized()

app.exec()
