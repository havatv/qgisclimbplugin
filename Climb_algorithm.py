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
                       #QgsProcessingUtils,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterRasterLayer,
                       QgsProcessingParameterBand,
                       QgsProcessingOutputNumber,
                       QgsWkbTypes,
                       # QgsProcessingException,
                       # QgsVectorLayer,
                       QgsFields,
                       QgsField)
from qgis.utils import Qgis
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
    MINELEVATION = 'MINELEVATION'
    MAXELEVATION = 'MAXELEVATION'
    CLIMBATTRIBUTE = 'climb'
    DESCENTATTRIBUTE = 'descent'
    MINELEVATTRIBUTE = 'minelev'
    MAXELEVATTRIBUTE = 'maxelev'

    # Override checking of parameters
    def checkParameterValues(self, parameters, context):
        super().checkParameterValues(parameters, context)
        source = self.parameterAsSource(parameters, self.INPUT, context)
        # Check for Z values
        hasZ = QgsWkbTypes.hasZ(source.wkbType())
        if not hasZ:
            if Qgis.QGIS_VERSION_INT < 30405:
                return [False, 'The line layer has no Z values, ' +
                        'so a DEM is needed, but extracting Z ' +
                        'values from the DEM requires QGIS ' +
                        '3.4.5 or later. Your QGIS version is ' +
                        Qgis.QGIS_VERSION +
                        ' - sorry about that!']
            demraster = self.parameterAsRasterLayer(parameters,
                                            self.DEMFORZ, context)
            if not demraster:
                return [False, 'The line layer has no Z values - ' +
                        'a DEM is needed']
            else:
                return [True, 'OK']
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
                self.tr('Input (line) layer'),
                [QgsProcessing.TypeVectorLine]
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

        # We add a feature sink in which to store our processed features.
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Climb layer')
            )
        )

        # Output number for total climb
        self.addOutput(
            QgsProcessingOutputNumber(
                self.TOTALCLIMB,
                self.tr('Total climb')
            )
        )

        # Output number for total descent
        self.addOutput(
            QgsProcessingOutputNumber(
                self.TOTALDESCENT,
                self.tr('Total descent')
            )
        )

        # Output number for minimum elevation
        self.addOutput(
            QgsProcessingOutputNumber(
                self.MINELEVATION,
                self.tr('Minimum elevation')
            )
        )

        # Output number for maximum elevation
        self.addOutput(
            QgsProcessingOutputNumber(
                self.MAXELEVATION,
                self.tr('Maximum elevation')
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
        # Add fields to the output layer
        # Add fields from the input layer
        thefields = QgsFields()
        climbindex = -1
        descentindex = -1
        fieldnumber = 0
        # Skip fields with names that are equal to the generated ones
        for field in source.fields():
            if str(field.name()) == str(self.CLIMBATTRIBUTE):
                feedback.pushInfo("Warning: existing " +
                                  str(self.CLIMBATTRIBUTE) +
                                  " attribute found and removed")
                climbindex = fieldnumber
            elif str(field.name()) == str(self.DESCENTATTRIBUTE):
                feedback.pushInfo("Warning: existing " +
                                  str(self.DESCENTATTRIBUTE) +
                                  " attribute found and removed")
                descentindex = fieldnumber
            else:
                thefields.append(field)
            fieldnumber = fieldnumber + 1
        # Create new fields for climb and descent
        thefields.append(QgsField(self.CLIMBATTRIBUTE, QVariant.Double))
        thefields.append(QgsField(self.DESCENTATTRIBUTE, QVariant.Double))
        thefields.append(QgsField(self.MINELEVATTRIBUTE, QVariant.Double))
        thefields.append(QgsField(self.MAXELEVATTRIBUTE, QVariant.Double))

        # If a DEM is provided, use it to extract z values
        if demraster:
            # Get the raster band with the z value
            demband = self.parameterAsString(parameters,
                                             self.BANDDEM,
                                             context)
            feedback.pushInfo("Adding Z values from DEM...")
            # Add the z values
            # if Qgis.QGIS_VERSION_INT >= 30505:  # is_child_algorithm
            withz = processing.run("native:setzfromraster",
                                 {"INPUT": parameters[self.INPUT],
                                  "RASTER": demraster,
                                  "BAND": demband,
                                  "OUTPUT": "memory:"},
                                 context=context,
                                 feedback=feedback,
                                 is_child_algorithm=True)["OUTPUT"]
            # else:
            #     withz = processing.run("native:setzfromraster",
            #                      {"INPUT": parameters[self.INPUT],
            #                       "RASTER": demraster,
            #                       "BAND": demband,
            #                       "OUTPUT": "memory:"},
            #                      context=context,
            #                      feedback=feedback,
            #                      ......... )["OUTPUT"]

            feedback.pushInfo("Z values added.")
            layerwithz = context.temporaryLayerStore().mapLayer(withz)
            # layerwithz = QgsProcessingUtils.mapLayerFromString(
            #                                         withz, context)
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
        minelevation = 0
        maxelevation = 0
        firstfeature = True
        for current, feature in enumerate(features):
            # Stop the algorithm if cancelled
            if feedback.isCanceled():
                break
            climb = 0
            descent = 0
            minelev = 0
            maxelev = 0
            # In case of multigeometries we need to do the parts
            for part in feature.geometry().constParts():
                # Calculate the climb
                first = True
                zval = 0
                for v in part.vertices():
                    zval = v.z()
                    # Check if we do not have a valid z value
                    if math.isnan(zval):
                        feedback.pushInfo("Missing Z value")
                        continue
                    if first:
                        prevz = zval
                        minelev = zval
                        maxelev = zval
                        first = False
                    else:
                        diff = zval - prevz
                        if diff > 0:
                            climb = climb + diff
                        else:
                            descent = descent - diff
                        if minelev > zval
                            minelev = zval
                        if maxelev < zval
                            maxelev = zval
                    prevz = zval
                totalclimb = totalclimb + climb
                totaldescent = totaldescent + descent
            # Set the attribute values
            attrs = feature.attributes()
            outattrs = []
            attrindex = 0
            for attr in attrs:
                # Skip attributes from the input layer that had names
                # that were equal to the generated ones
                if not (attrindex == climbindex or
                        attrindex == descentindex):
                    outattrs.append(attr)
                attrindex = attrindex + 1
            #feature.setAttributes(outattrs + [climb, descent])
            feature.setAttributes(outattrs + [climb, descent, minelev, maxelev])
            # Add a feature to the sink
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            if firstfeature:
                minelevation = minelev
                maxelevation = maxelev
                firstfeature = False
            else:
                if minelevation > minelev
                    minelevation = minelev
                if maxelevation < maxelev
                    maxelevation = maxelev
            # Update the progress bar
            if fcount > 0:
                feedback.setProgress(int(100 * current / fcount))
        # Return the results
        return {self.OUTPUT: dest_id, self.TOTALCLIMB: totalclimb,
                self.TOTALDESCENT: totaldescent,
                self.MINELEVATION: minelevation,
                self.MAXELEVATION: maxelevation}

    def shortHelpString(self):
        return("The total climb and descent along the line "
               "geometries of the input line layer are calculated "
               "using the Z values for the points making up "
               "the lines.<br> "
               "Z values can be provided by the line geometries or "
               "a DEM (by using the <i>Drape (set z-value from "
               "raster)</i> algorithm to assign Z values to the "
               "points that make up the lines).<br> "
               "If a DEM is specified, Z values will be taken from "
               "the DEM and not the line layer.<br>"
               "The output layer (OUTPUT) has extra fields "
               "(<i>climb</i> and <i>descent</i>) "
               "that shall contain the total climb "
               "and the total descent for each line geometry, "
               "and extra fields (<i>minelev</i> and <i>maxelev</i>) "
               "that shall contain the minimum and maximum elevation "
               "of each line geometry."
               "If these fields exist in the input layer the "
               "original fields will be removed.<br>"
               "The layer totals are returned in the TOTALCLIMB, "
               "TOTALDESCENT, MINELEVATION and MAXELEVATION output "
               "parameters.")

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
