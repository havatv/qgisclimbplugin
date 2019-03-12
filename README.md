# qgisclimbplugin
<h1>Climb</h1>

<i>Climb</i> is a QGIS Processing Plugin that calculates the total
climb (and descent) along the lines of a line layer based on Z values
taken from the lines or extracted from a supplied DEM.
The algorithm is placed under <i>Vector analysis</i> in the
<i>Processing Toolbox</i>.

<h2>Parameters</h2>
<dl>
    <dt>INPUT</dt>
    <dd>The input vector layer (has to be a line layer).</dd>
    <dt>DEMFORZ</dt>
    <dd>A raster layer to be used as a DEM to extract Z values for
        the lines in the input vector layer (optional).</dd>
    <dt>BANDDEM</dt>
    <dd>The band to use in the DEM (DEMFORZ) layer.</dd>
    <dt>OUTPUT</dt>
    <dd>The <b>output</b> vector layer.
        It will be a copy of the input vector layer, but with two
        new attributes (<i>climb</i> and <i>descent<i>) containing
        the climb and descent for each line.
        Input attributes with the same names will be removed.
        </dd>
    <dt>TOTALCLIMB</dt>
    <dd><b>Output</b> parameter that contains the total climb for all
        the lines of the input laye.r</dd>
    <dt>TOTALDESCENT</dt>
    <dd><b>Output</b> parameter that contains the total descent for
        all the lines of the input layer.</dd>
</dl>
