#!/usr/bin/env python

import sys
import numpy as np
import scipy as sp
import matplotlib as mpl
from matplotlib import pyplot as plt

from typing import Tuple, Type, Optional

import PyQt6
from PyQt6 import QtWidgets
from PyQt6.QtWidgets import QApplication, QMainWindow

from matplotlib.backends.backend_qt5agg import FigureCanvas
from matplotlib.figure import Figure

from shifters import OpticalAxisShifter, EllipticShifter
from transformers import LinearTransformer, ExponentialTransformer, BiexponentialTransformer
from projections import Projection, BorovickaProjection


mpl.use('Qt5Agg')

COUNT = 100


class Fitter():
    def __init__(self):
        pass

    def __call__(self, xy: Tuple[np.ndarray, np.ndarray], za: Tuple[np.ndarray, np.ndarray], cls: Type[Projection], *, params: Optional[dict]=None) -> Projection:
        """
            xy      a 2-tuple of x and y coordinates on the sensor
            za      a 2-tuple of z and a coordinates in the sky catalogue
            cls     a subclass of Projection that is used to transform xy onto za
            Returns an instance of cls with parameters set to values that result in minimal deviation
        """
        return cls(params)


class Vascop():
    """ Virtual All-Sky CorrectOr Plate """
    def __init__(self):
        self.argparser = argparse.ArgumentParser("Virtual all-sky corrector plate")
        self.argparser.add_argument('infile', type=argparse.FileType('r'), help="input file")
        self.argparser.add_argument('outdir', action=argparser.WriteableDir, help="output directory")
        self.argparser.add_argument('method', type=str, choices=Corrector.METHODS)
        self.args = self.argparser.parse_args()
        self.outdir = Path(self.args.outdir)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Virtual All-Sky CorrectOr Plate")

        self.spinBox = QtWidgets.QDoubleSpinBox()
        self.spinBox.setMinimum(-1)
        self.spinBox.setSingleStep(0.001)
        self.spinBox.setMaximum(1)

        self.figure = Figure(figsize=(5, 5))
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.subplots(1, 2)
        self.figure.tight_layout()
        self.plot()

        self.entire = QtWidgets.QWidget()
        self.globalLayout = QtWidgets.QGridLayout()
        self.entire.setLayout(self.globalLayout)
        self.setCentralWidget(self.entire)

        self.control = QtWidgets.QGroupBox(self)
        self.control.setTitle("Controls")
        self.controlLayout = QtWidgets.QGridLayout()

        self.add_spinbox(self.control, "x0", 0)
        self.add_spinbox(self.control, "y0", 1)
        self.add_spinbox(self.control, "a0", 2)

        self.control.setLayout(self.controlLayout)
        self.globalLayout.addWidget(self.control)


    def add_spinbox(self, parent, title, column):
        spinbox = QtWidgets.QDoubleSpinBox(parent)
        spinbox.setMinimum(-100)
        spinbox.setMaximum(100)
        spinbox.setValue(0)
        spinbox.setSingleStep(0.1)
        spinbox.setDecimals(6)
        spinbox.valueChanged.connect(self.plot)

        label = QtWidgets.QLabel()
        label.setText(title)

        self.controlLayout.addWidget(label, 0, column, 1, 1)
        self.controlLayout.addWidget(spinbox, 1, column, 1, 1)
        return spinbox



    def plot(self):
        x = np.random.normal(0, 0.3, size=COUNT)
        y = np.random.normal(0, 0.3, size=COUNT)
        self.ax[0].scatter(x, y)
        print("Piči")



app = QApplication(sys.argv)

window = MainWindow()
window.show()

app.exec()
