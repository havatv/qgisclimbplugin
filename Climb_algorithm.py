# -*- coding: utf-8 -*-

"""
/***************************************************************************
 Climb
                                 A QGIS plugin

                              -------------------
        begin                : 2019-03-01
        copyright            : (C) 2019 by Håvard Tveite
        email                : havard.tveite@nmbu.no
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = 'Håvard Tveite'
__date__ = '2019-03-01'
__copyright__ = '(C) 2019 by Håvard Tveite'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import math
from PyQt5.QtCore import QCoreApplication, QVariant
from qgis.core import (QgsProcessing,
                       QgsFeatureSink,
                       QgsProcessingAlgorithm,
                       QgsProcessingUtils,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterRasterLayer,
                       QgsProcessingParameterBand,
                       QgsWkbTypes,
                       QgsProcessingException,
                       QgsVectorLayer,
                       QgsField)
import processing


class ClimbAlgorithm(QgsProcessingAlgorithm):
    """
    Takes a line vector layer and calculates climb.
    Returns the total climb of the lines and a line vector layer
    that includes the climb for each line.
    """

    # Constants used to refer to parameters and outputs. They will be
    # used when calling the algorithm from another algorithm, or when
    # calling from the QGIS console.

    OUTPUT = 'OUTPUT'
    INPUT = 'INPUT'
    DEMFORZ = 'DEMFORZ'
    BANDDEM = 'BANDDEM'
    TOTALCLIMB = 'TOTALCLIMB'
    TOTALDESCENT = 'TOTALDESCENT'

    # Override checking of parameters
    def checkParameterValues(self, parameters, context):
        super().checkParameterValues(parameters, context)
        source = self.parameterAsSource(parameters, self.INPUT, context)
        # Check for Z values
        hasZ = QgsWkbTypes.hasZ(source.wkbType())
        if not hasZ:
            demraster = self.parameterAsRasterLayer(parameters,
                                            self.DEMFORZ, context)
            if not demraster:
                return [False, 'The line layer has no z values - ' +
                        'a DEM is needed']
            else:
                return [True, 'OK']

    def initAlgorithm(self, config):
        """
        Here we define the inputs and output of the algorithm, along
        with some other properties.
        """

        # We add the input vector features source. Has to be of type
        # line.
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr('Input layer'),
                [QgsProcessing.TypeVectorLine]
            )
        )

        # We add a feature sink in which to store our processed features.
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Output layer')
            )
        )

        # DEM for extracting the z value
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.DEMFORZ,
                self.tr('DEM (to get Z values)'),
                optional=True
            )
        )

        # Raster band containing the z value (DEM)
        self.addParameter(
            QgsProcessingParameterBand(
                self.BANDDEM,
                self.tr('Band containing the Z values)'),
                None,
                self.DEMFORZ
            )
        )

        # Output number for total climb
        self.addParameter(
            QgsProcessingParameterNumber(
                self.TOTALCLIMB,
                self.tr('Total climb'),
                type=QgsProcessingParameterNumber.Double
            )
        )

        # Output number for total descent
        self.addParameter(
            QgsProcessingParameterNumber(
                self.TOTALDESCENT,
                self.tr('Total descent'),
                type=QgsProcessingParameterNumber.Double
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        """
        Here is where the processing itself takes place.
        """
        # Get the feature source
        source = self.parameterAsSource(parameters, self.INPUT, context)
        # Get the number of features (for the progress bar)
        fcount = source.featureCount()
        # Check for Z values
        hasZ = QgsWkbTypes.hasZ(source.wkbType())
        # Get the DEM
        demraster = self.parameterAsRasterLayer(parameters,
                                                self.DEMFORZ,
                                                context)
        # Create fields for climb and descent
        thefields = source.fields()
        thefields.append(QgsField("climb", QVariant.Double))
        thefields.append(QgsField("descent", QVariant.Double))

        #if not hasZ and demraster:
        # If a DEM is provided, use it to extract z values
        if demraster:
            # Get the raster band with the z value
            demband = self.parameterAsString(parameters,
                                             self.BANDDEM,
                                             context)
            feedback.pushInfo("Adding Z values from DEM...")
            # Add the z values
            withz = processing.run("native:setzfromraster",
                                 {"INPUT": parameters[self.INPUT],
                                  "RASTER": demraster,
                                  "BAND": demband,
                                  "OUTPUT": "memory:"},
                                 context=context,
                                 feedback=feedback,
                                 is_child_algorithm=True)["OUTPUT"]
            feedback.pushInfo("Z values added.")
            layerwithz = context.temporaryLayerStore().mapLayer(withz)
            #layerwithz = QgsProcessingUtils.mapLayerFromString(withz, context)
        else:
            layerwithz = source
        # Retrieve the feature sink. The 'dest_id' variable is used
        # to uniquely identify the feature sink, and must be included
        # in the dictionary returned by the processAlgorithm
        # function.
        (sink, dest_id) = self.parameterAsSink(parameters,
                                               self.OUTPUT,
                                               context, thefields,
                                               layerwithz.wkbType(),
                                               source.sourceCrs())

        # get features from source (with z values)
        features = layerwithz.getFeatures()
        totalclimb = 0
        totaldescent = 0
        for current, feature in enumerate(features):
            # Stop the algorithm if cancelled
            if feedback.isCanceled():
                break
            climb = 0
            descent = 0
            # In case of multigeometries we need to do the parts
            for part in feature.geometry().constParts():
                # Calculate the climb
                first = True
                zval = 0
                for v in part.vertices():
                    zval = v.z()
                    # Check if we do not have a valid z value
                    if math.isnan(zval):
                        feedback.pushInfo("Missing z value")
                        continue
                    if first:
                        prevz = zval
                        first = False
                    else:
                        diff = zval - prevz
                        if diff > 0:
                            climb = climb + diff
                        else:
                            descent = descent - diff
                    prevz = zval
                totalclimb = totalclimb + climb
                totaldescent = totaldescent + descent
            attrs = feature.attributes()
            feature.setAttributes(attrs + [climb, descent])

            # Add a feature to the sink
            sink.addFeature(feature, QgsFeatureSink.FastInsert)

            # Update the progress bar
            if fcount > 0:
                feedback.setProgress(int(100 * current / fcount))

        # Return the results
        return {self.OUTPUT: dest_id, self.TOTALCLIMB: totalclimb,
                self.TOTALDESCENT: totaldescent}

    def shortHelpString(self):
        return("Calculates the total climb and descent along lines "
               "using Z values.<br>"
               "Z values can be provided by the line geometries or "
               "by a DEM (using the <i>Drape (set z-value from "
               "raster)</i> algorithm).<br>"
               "If a DEM is specified, Z values will be taken from "
               "the DEM and not the line layer.")

    def name(self):
        """
        Returns the algorithm name, used for identifying the
        algorithm. This string must not be localised.  Names should
        contain lowercase alphanumeric characters only and no spaces
        or other formatting characters.
        """
        return 'climbalongline'

    def displayName(self):
        """
        Returns the translated algorithm name (for display).
        """
        return self.tr("Climb along line")

    def group(self):
        """
        Returns the name of the group this algorithm belongs to.
        This string should be localised.
        """
        return self.tr('Vector analysis')

    def groupId(self):
        """
        Returns the unique ID of the group this algorithm belongs to.
        This string must not be localised.
        Group id should contain lowercase alphanumeric characters
        only and no spaces or other formatting characters.
        """
        # return 'Climb'
        return 'vectoranalysis'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return ClimbAlgorithm()
