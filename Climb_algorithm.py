# -*- coding: utf-8 -*-

"""
/***************************************************************************
 Climb
                                 A QGIS plugin
 Climb
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2019-03-01
        copyright            : (C) 2018 by Håvard Tveite
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

from PyQt5.QtCore import QCoreApplication, QVariant
from qgis.core import (QgsProcessing,
                       QgsFeatureSink,
                       QgsProcessingAlgorithm,
                       #QgsProcessingParameters,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterRasterLayer,
                       QgsProcessingParameterBand,
                       QgsWkbTypes,
                       QgsField)


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

        # Retrieve the feature source and sink. The 'dest_id' variable is used
        # to uniquely identify the feature sink, and must be included in the
        # dictionary returned by the processAlgorithm function.
        source = self.parameterAsSource(parameters, self.INPUT, context)
        demraster = self.parameterAsRasterLayer(parameters, self.DEMFORZ,
                context)
        feedback.pushInfo("DEM raster: " + str(demraster))
        # Check for Z values
        hasZ = QgsWkbTypes.hasZ(source.wkbType())
        feedback.pushInfo("Line layer has Z values: " + str(hasZ))
        if not hasZ and demraster is None:
            feedback.reportError("The line layer has no Z values - please specify a DEM raster")
            return {self.OUTPUT: None, self.TOTALCLIMB: 0, self.TOTALDESCENT: 0}

        # Create fields for climb and descent
        thefields = source.fields()
        thefields.append(QgsField("climb", QVariant.Double))
        thefields.append(QgsField("descent", QVariant.Double))
        # The wkbType could be wrong (in case there is no z values in the original)
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT,
                context, thefields, source.wkbType(), source.sourceCrs())

        if not hasZ:
            # Get the raster band with the z value
            demband = self.parameterAsString(parameters, self.BANDDEM, context)

            # Add the z values
            layerwithz = run("native:setzfromraster", {
                                  INPUT=source,
                                  RASTER=demraster,
                                  BAND=demband
                                  OUTPUT="memory:"})["OUTPUT"]
        else:
            layerwithz = source
        
        # Compute the number of steps to display within the progress bar and
        # get features from source
        total = 100.0 / source.featureCount() if source.featureCount() else 0
        features = source.getFeatures()
        #features = layerwithz.getFeatures()
        totalclimb = 0
        totaldescent = 0
        for current, feature in enumerate(features):
            # Stop the algorithm if cancel button has been clicked
            if feedback.isCanceled():
                break
            climb = 0
            descent = 0
            # Handle multigeometries
            for part in feature.geometry().constParts():
                # Calculate the climb
                first = True
                zval = 0
                for v in part.vertices():
                    zval = v.z()
                    #feedback.pushInfo("z value: " + str(zval))
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
            #feedback.pushInfo("climb: " + str(climb))
            #feedback.pushInfo("descent: " + str(descent))
            attrs = feature.attributes()
            #feature["climb"] = climb
            #feature["descent"] = descent
            feature.setAttributes(attrs+[climb, descent])

            # Add a feature in the sink
            sink.addFeature(feature, QgsFeatureSink.FastInsert)

            # Update the progress bar
            feedback.setProgress(int(current * total))

        # Return the results of the algorithm. In this case our only result is
        # the feature sink which contains the processed features, but some
        # algorithms may return multiple feature sinks, calculated numeric
        # statistics, etc. These should all be included in the returned
        # dictionary, with keys matching the feature corresponding parameter
        # or output names.
        return {self.OUTPUT: dest_id, self.TOTALCLIMB: totalclimb, self.TOTALDESCENT: totaldescent}

    def name(self):
        """
        Returns the algorithm name, used for identifying the algorithm. This
        string should be fixed for the algorithm, and must not be localised.
        The name should be unique within each provider. Names should contain
        lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'climbalongline'

    def displayName(self):
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return self.tr("Climb along line")

    def group(self):
        """
        Returns the name of the group this algorithm belongs to. This string
        should be localised.
        """
        return self.tr(self.groupId())

    def groupId(self):
        """
        Returns the unique ID of the group this algorithm belongs to. This
        string should be fixed for the algorithm, and must not be localised.
        The group id should be unique within each provider. Group id should
        contain lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'Vector analysis'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return ClimbAlgorithm()
