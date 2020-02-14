import logging
from enum import Enum, unique

import numpy as np
from palettable.cartocolors.qualitative import Bold_10 as LightPalette
from palettable.cartocolors.qualitative import Pastel_10 as DarkPalette
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter, SVGExporter
from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import QFont
from PySide2.QtWidgets import QGridLayout, QPushButton, QWidget

from models.FittingResult import FittingResult
from models.SampleData import SampleData

@unique
class XAxisSpace(Enum):
    Raw = 0
    Log10 = 1
    Phi = 2

class DistributionCanvas(QWidget):
    sigExpectedMeanValueChanged = Signal(tuple)
    logger = logging.getLogger("root.ui.DistributionCanvas")
    gui_logger = logging.getLogger("GUI")

    def __init__(self, parent=None, light=True, **kargs):
        super().__init__(parent, **kargs)
        self.set_skin_mode(light)
        self.init_ui()

    def set_skin_mode(self, light: str):
        if light:
            pg.setConfigOptions(foreground=pg.mkColor("k"))
            # prepare styles
            self.target_style = dict(pen=None, symbol="o", symbolBrush=pg.mkBrush("#161B26"), symbolPen=None, symbolSize=5)
            self.sum_style = dict(pen=pg.mkPen("#062170", width=3))
            self.component_styles = [dict(pen=pg.mkPen(hex_color, width=2, style=Qt.DashLine)) for hex_color in LightPalette.hex_colors]
            # Due to the bug of pyqtgraph, can not perform the foreground to labels
            self.label_styles = {"font-family": "Times New Roman", "color": "black"}
        else:
            pg.setConfigOptions(foreground=pg.mkColor("w"))
            self.target_style = dict(pen=None, symbol="o", symbolBrush=pg.mkBrush("#afafaf"), symbolPen=None, symbolSize=5)
            self.sum_style = dict(pen=pg.mkPen("#062170", width=3))
            self.component_styles = [dict(pen=pg.mkPen(hex_color, width=2, style=Qt.DashLine)) for hex_color in DarkPalette.hex_colors]
            self.label_styles = {"font-family": "Times New Roman", "color": "white"}

    def init_ui(self):
        self.main_layout = QGridLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.plot_widget = pg.PlotWidget(enableMenu=False)
        self.main_layout.addWidget(self.plot_widget, 0, 0)
        # add image exporters
        self.png_exporter = ImageExporter(self.plot_widget.plotItem)
        self.svg_exporter = SVGExporter(self.plot_widget.plotItem)
        # prepare the plot data item for target and fitted data
        self.target_item = pg.PlotDataItem(name="Target", **self.target_style)
        self.plot_widget.plotItem.addItem(self.target_item)
        self.fitted_item = pg.PlotDataItem(name="Fitted", **self.sum_style)
        self.plot_widget.plotItem.addItem(self.fitted_item)
        # set labels
        self.plot_widget.plotItem.setLabel("left", self.tr("Probability Density"), **self.label_styles)
        self.plot_widget.plotItem.setLabel("bottom", self.tr("Grain size")+" (μm)", **self.label_styles)
        # set title
        self.title_format = """<font face="Times New Roman">%s</font>"""
        self.plot_widget.plotItem.setTitle(self.title_format % self.tr("Distribution Canvas"))
        # show grids
        self.plot_widget.plotItem.showGrid(True, True)
        self.tick_font = QFont("Arial")
        self.tick_font.setPointSize(8)
        # set all axes
        for axis_name in ["left", "top", "right", "bottom"]:
            self.plot_widget.plotItem.showAxis(axis_name)
            # set the font of ticks
            self.plot_widget.plotItem.getAxis(axis_name).tickFont = self.tick_font
            self.plot_widget.plotItem.getAxis(axis_name).enableAutoSIPrefix(enable=False)
        # set legend
        self.legend_format = """<font face="Times New Roman">%s</font>"""
        self.legend = pg.LegendItem(offset=(80, 50))
        self.legend.setParentItem(self.plot_widget.plotItem)
        self.legend.addItem(self.target_item, self.legend_format % self.tr("Target"))
        self.legend.addItem(self.fitted_item, self.legend_format % self.tr("Fitted"))

        self.x_axis_space = XAxisSpace.Log10
        self.component_curves = []
        self.component_lines = []
        self.position_limit = None
        self.position_cache = []

    def raw2space(self, value: float) -> float:
        processed = value
        if self.position_limit is not None:
            lower, upper = self.position_limit
            if processed < lower:
                processed = lower
            elif processed > upper:
                processed = upper
        if self.x_axis_space == XAxisSpace.Raw:
            return processed
        elif self.x_axis_space == XAxisSpace.Log10:
            return np.log10(processed)
        elif self.x_axis_space == XAxisSpace.Phi:
            return -np.log2(processed)
        else:
            raise NotImplementedError(self.x_axis_space)

    def space2raw(self, value: float) -> float:
        if self.x_axis_space == XAxisSpace.Raw:
            processed = value
        elif self.x_axis_space == XAxisSpace.Log10:
            processed = 10**value
        elif self.x_axis_space == XAxisSpace.Phi:
            processed = 2**(-value)
        else:
            raise NotImplementedError(self.x_axis_space)
        if self.position_limit is not None:
            lower, upper = self.position_limit
            if processed < lower:
                processed = lower
            elif processed > upper:
                processed = upper
        return processed

    def on_line_position_changed(self, current_line):
        for i, line in enumerate(self.component_lines):
            if current_line is line:
                raw_value = self.space2raw(current_line.getXPos())
                current_line.setValue(self.raw2space(raw_value))
                self.position_cache[i] = raw_value
        self.sigExpectedMeanValueChanged.emit(tuple(self.position_cache))

    def on_component_number_changed(self, component_number: int):
        self.logger.info("Received the component changed signal, start to clear and add data items.")
        # Check the validity of `component_number`
        if type(component_number) != int:
            raise TypeError(component_number)
        if component_number <= 0:
            raise ValueError(component_number)
        # clear
        for curve in self.component_curves:
            self.plot_widget.plotItem.removeItem(curve)
            self.legend.removeItem(curve)
        for line in self.component_lines:
            self.plot_widget.plotItem.removeItem(line)
        self.component_curves.clear()
        self.component_lines.clear()
        self.position_cache = np.ones(component_number)
        self.logger.debug("Items cleared.")
        # add
        for i in range(component_number):
            component_name = "C{0}".format(i+1)
            curve = pg.PlotDataItem(name=component_name,**self.component_styles[i%len(self.component_styles)])
            line = pg.InfiniteLine(angle=90, movable=False, pen=self.component_styles[i%len(self.component_styles)]["pen"])
            line.setMovable(True)
            line.sigDragged.connect(self.on_line_position_changed)
            self.plot_widget.plotItem.addItem(curve)
            self.plot_widget.plotItem.addItem(line)
            self.legend.addItem(curve, self.legend_format % component_name)
            self.component_curves.append(curve)
            self.component_lines.append(line)
        self.logger.debug("Items added.")

    def on_target_data_changed(self, sample: SampleData):
        # change the value space of x axis
        if self.x_axis_space == XAxisSpace.Raw:
            self.plot_widget.plotItem.setLogMode(x=False)
        elif self.x_axis_space == XAxisSpace.Log10:
            self.plot_widget.plotItem.setLogMode(x=True)
        else:
            raise NotImplementedError(self.x_axis_space)
        # the range to limit the positions of lines
        self.position_limit = (sample.classes[0], sample.classes[-1])
        all_ticks = [(self.raw2space(x_value), "{0:0.2f}".format(x_value)) for x_value in sample.classes]
        major_ticks = all_ticks[::20]
        minor_ticks = all_ticks[::5]
        self.plot_widget.plotItem.getAxis("top").setTicks([major_ticks, minor_ticks, all_ticks])
        self.plot_widget.plotItem.getAxis("bottom").setTicks([major_ticks, minor_ticks, all_ticks])
        self.logger.debug("Target data has been changed to [%s].", sample.name)
        # update the title of canvas
        if sample.name is None or sample.name == "":
            sample.name = "UNKNOWN"
        self.plot_widget.plotItem.setTitle(self.title_format % sample.name)
        # update target
        # target data (i.e. grain size classes and distribution) should have no nan value indeed
        # it should be checked during load data progress
        self.target_item.setData(sample.classes, sample.distribution, **self.target_style)
        self.fitted_item.clear()
        for curve in self.component_curves:
            curve.clear()
        for line in self.component_lines:
            line.setValue(1)

    def update_canvas_by_data(self, result: FittingResult, current_iteration=None):
        # update the title of canvas
        if current_iteration is None:
            self.plot_widget.plotItem.setTitle(self.title_format % result.name)
        else:
            self.plot_widget.plotItem.setTitle(
                self.title_format %
                ("{0} "+self.tr("Iteration")+" ({1})").format(
                    result.name, current_iteration))
        # update fitted
        self.fitted_item.setData(result.real_x, result.fitted_y, **self.sum_style)
        # update component curves
        for i, component, curve, line in zip(
                range(result.component_number),
                result.components,
                self.component_curves,
                self.component_lines):
            curve.setData(result.real_x, component.component_y, **self.component_styles[i%len(self.component_styles)])
            if np.isnan(component.mean) or np.isinf(component.mean):
                continue
            space_value = self.raw2space(component.mean)
            self.position_cache[i] = self.space2raw(space_value)
            line.setValue(space_value)

    def on_fitting_epoch_suceeded(self, result: FittingResult):
        self.update_canvas_by_data(result)
        self.png_exporter.export("./temp/distribution_canvas/png/{0} - {1} - {2}.png".format(
            result.name, result.distribution_type, result.component_number))
        self.svg_exporter.export("./temp/distribution_canvas/svg/{0} - {1} - {2}.svg".format(
            result.name, result.distribution_type, result.component_number))

    def on_single_iteration_finished(self, current_iteration: int, result: FittingResult):
        self.update_canvas_by_data(result, current_iteration=current_iteration)
