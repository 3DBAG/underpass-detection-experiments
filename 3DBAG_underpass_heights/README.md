# Underpass height detection

<ol>
  <li>Introduction</li>
  <li>General pipeline
    <ol>
      <li>Data preprocessing</li>
      <li>Perspective projection</li>
      <li>Facade texture extraction</li>
      <li>Height estimation methods</li>
      <li>Output data</li>
    </ol>
    </li>
  <li>Assessment of results</li>
      <ol type="1">
      <li>Data quality</li>
      <li>Connected components method</li>
      <li>Depth map model</li>
      <li>U-Net model</li>
      </ol>
    </li>
    <li>Running the code</li>
  </li>
</ol>

## 1. Introduction

## 2. General pipeline

![General pipeline](md_images/general_pipeline.jpg)
<p align="center">
  <strong>Figure 1:</strong> General pipeline
</p>

<p>
The general pipeline is depicted in <strong>Figure 1</strong>. The code takes as inputs the underpasses polygons in GeoJSON format, a data set of oblique images with their corresponding camera parameters and image footprints polygons (<i>camera_parameters.txt, image_footprints.geojson</i>) and a set of 3D BAG tiles in GeoPackage format. 

The code iterates over each 3D BAG tile, and updates the estimated height of each observed underpass. Once it has iterated over all tiles, writes a GeoJSON file with final height estimations for each underpass.

A more detailed description of each step is given in the upcoming sections.
</p>

### 2.1. Data preprocessing
<p>
The script <strong>data_preprocessing.py</strong> contains the functions for loading and processing input data. It fulfills the following tasks:

1. Loads the camera parameters, the image footprints, the underpass polygons into <i>GeoDataFrames</i>.

2. In each iteration, loads the corresponding lod-0 (building footprints) and lod-22 (3D buildings) geometries in two different <i>GeoDataFrames</i>.

3. Finds the underpass polygons which match the building footprints of the 3D BAG tile, and computes <strong>critical segments</strong>. The critical segments are the intersection between the underpass polygon boundary (buffered) and the building footprint boundary. This segments match the openings of the underpass. <strong>Figure 2</strong> shows four examples of computed critical segments and their corresponding facades in real life.

<table align="center">
<tr>
<td align="center">
<img src="md_images/critical_segments.jpg" height="250"><br>
</td>

<td align="center">
<img src="md_images/critical_segments_3d.jpg" height="250"><br>
</td>
</tr>
</table>
<p align="center">
  <strong>Figure 2:</strong> Critical segments and their corresponding facades with underpass openings.
</p>

4. Computes the critical walls, which are 3D equivalents to the critical segments. This is done by intersecting the critical segments (buffered) with the 3D building geometries, which returns a set of 3D polygons (walls). Out of this set, we are interested in <strong>min_z</strong> and <strong>max_z</strong>. We will use these values combined with the critical segment coordinates to construct the critical wall geometry. The height of the critical wall is computed as <strong>max_z</strong> - <strong>min_z</strong> and stored as an attribute. <strong>Figure 3</strong> the corresponding critical walls of the critical segments shown in <strong>Figure 2</strong>.


<p align="center">
  <img src="md_images/critical_walls.jpg" width="500">
</p>
<p align="center">
  <strong>Figure 3:</strong> Computed critical walls in 3D view.
</p>

5. Constructs an <strong>image-wall</strong> visibility table. This is the most crucial step as it relates each image to a set of visible walls, which is later used in perspective projection. 
   <strong>Table 1</strong> shows an example of the output of such a table.

   <p align="center">
     <strong>Table 1:</strong> Image-wall visibility table.
   </p>


    <div align="center">

   | image_id              | visible_walls                         | camera_x       | camera_y       | camera_z   |
   |-----------------------|---------------------------------------|---------------:|---------------:|-----------:|
   | 402_0029_00131903.tif | [421, 422]                            | 142547.567520 | 488023.933861 | 445.913029 |
   | 402_0029_00131904.tif | [419, 420, 421, 422]                  | 142450.086788 | 488023.509496 | 444.967591 |
   | 402_0029_00131907.tif | []                                    | 142250.161996 | 488022.982741 | 444.541843 |
   | 402_0030_00131343.tif | [464, 298, 297]                       | 143708.653197 | 487789.798263 | 430.346762 |
   | 402_0030_00131344.tif | [465, 464, 461, 462, 298, 297, ...]   | 143807.812084 | 487789.429113 | 429.582020 |

    </div>

    The table is computed by first intersecting the image footprint polygons with the critical wall geometries. This creates a list of intersected wall_ids for each image. However, not all walls in this list are visible/valid. Therefore, we must filter according to the following criteria (<strong>Figure 4</strong>):
    <p> a) The normal of the wall is pointing towards the camera plane.</p>
    <p> b) The angle between the normal of the wall and the normal of the camera plane (θ) is less than a limit angle.</p>

  <table align="center">
    <tr>
    <td align="center">
    <img src="md_images/criteria_a.jpg" height="300"><br>
    </td>
    <td align="center">
    <img src="md_images/criteria_b.jpg" height="300"><br>
    </td>
    </tr>
    </table>

   <p align="center">
     <strong>Figure 4:</strong> Filtering criteria to determine wall visibility
   </p>

  <div style="border-left:5px solid #4a90e2; padding:10px;">
    <strong>Suggestion:</strong> In future implementations investigate facade occlusion as filtering criteria
    </div>
</p>

### 2.2. Perspective projection
The module <strong>perspective_projection.py</strong> contains all functions to project critical wall geometries (encoded in EPSG:7415) onto the image plane. The code iterates through every row in the <strong>image-wall</strong> visibility table, performs the following tasks:

1. Extracts all visible walls per image

2. Computes the camera matrix $K$ for the current image. We can easily define it using the parameters in <strong>camera_parameters.txt</strong> as follows.

$$
K = 
\begin{bmatrix}
f_x & 0 & c_x \\
0 & f_y & c_y \\
0 & 0 & 1
\end{bmatrix}
$$

3. Calculates the rotation matrix $R = R_\kappa \times \times R_\phi \times R_\omega $. We can find the angles $\kappa$, $\phi$ and $\omega$ in <strong>camera_parameters.txt</strong>, and then compute:

<table>
<tr>
<td align="center">

$$
R_\omega =
\begin{bmatrix}
1 & 0 & 0 \\
0 & \cos\omega & -\sin\omega \\
0 & \sin\omega & \cos\omega
\end{bmatrix}
$$

</td>
<td align="center"> 

$$
R_\phi =
\begin{bmatrix}
\cos\phi & 0 & \sin\phi \\
0 & 1 & 0 \\
-\sin\phi & 0 & \cos\phi
\end{bmatrix}
$$

</td>
<td align="center">

$$
R_\kappa =
\begin{bmatrix}
\cos\kappa & -\sin\kappa & 0 \\
\sin\kappa & \cos\kappa & 0 \\
0 & 0 & 1
\end{bmatrix}
$$

</td>
</tr>
</table>

<div style="border-left:5px solid #4a90e2; padding:10px;">
    <strong>Caution:</strong> The multiplication order of rotation matrices depends on the convention chosen for the rotation angles. The given order <code>R = Rκ Rφ Rω</code> is standard for photogrammetry datasets, however, this might be different in your dataset (e.g. <code>R = Rω Rφ Rκ</code>).
</div>

<div style="border-left:5px solid #4a90e2; padding:10px;">
    <strong>Caution:</strong> <code>R</code> might need to be transposed <code>R = R.T</code>. This applies when the rotation matrices are defined as rotations from the camera axes to the world axes. 
</div>


4. Computes the translation vector $t$. This is straightforward when knowing the camera position $X, Y, Z$, which are defined in <strong>camera_parameters.txt</strong>

$$
t = 
- R \times 
\begin{bmatrix}
X \\
Y \\
Z
\end{bmatrix}
$$


5. Computes the projection matrix $M$ for the current image.

$$
M = K \; [R \mid t]
$$


6. For each visible wall, extracts the wall geometry and projects it onto the image plane using the projection matrix $M$.

   $$
   \begin{bmatrix} u_h \\ v_h \\ w_h \end{bmatrix} 
   = M \, X_w 
   $$

   The 2D pixel coordinates are obtained by normalizing the homogeneous coordinates.

   $$
   u = \frac{u_h}{w_h}, \quad v = \frac{v_h}{w_h}
   $$

<strong>Figure 5</strong> shows an example of critical walls projected onto the oblique image plane. These  2D polygons will be used in the facade texture extraction.

<p align="center">
  <img src="md_images/projected_walls.jpg" width="500">
</p>
<p align="center">
  <strong>Figure 5:</strong> Perspective projection of critical walls onto an oblique image
</p>

<div style="border-left:5px solid #4a90e2; padding:10px;">
    <strong>Caution:</strong> The application of this method relies enormously on the quaity of the oblique image data set. Small errors or inconsistencies in the camera parameters will lead to wrong projections, which will ultimately affect the height estimation. Moreover, multi-cameras data sets might need particular adjustments for each camera (depending on their orientation). In summary, data accuracy is a must, and orientation consistency in all cameras is highly appreciated to increase the generalization of the method.
</div>

</p>

### 2.3. Facade texture extraction

The module <strong>facade_extraction.py</strong> includes the functions to extract, reproject and visualize the facade txtures corresponding to the critical walls. This process is done by iterating over the 2D polygons resulting from the critical wall projection onto the image plane. For each polygon:

1. Reorder the polygon coordinates to make sure that the reprojection is done cosnistently.

2. Compute the <strong>width</strong> and the <strong>height</strong> of the output reprojected facade.

3. The output image rectangle will be defined as:

  ```code
output_rectangle = np.array([
                [0, 0],
                [0, height-1],
                [width-1, height-1],
                [width-1, 0]
            ], dtype="float32")
  ```

4.  Apply the reprojection by establishing point correspondances between the 2D polygon and the output rectangle.

Assuming that the extracted facade image height corresponds to the height of the facade in the real world, we will be able to determine the height of the underpasss ceiling by establishing a proportion (pixel - meters). However, we must consider that vertical distances are distorted to a lesser or bigger extent. The ideal situation is when the camera plane is parallel to the facade. <strong>Figure 6 </strong> shows an example of an extracted facade texture.

<p align="center">
  <img src="md_images/extracted_facade.jpg" width="300">
</p>

<p align="center">
  <strong>Figure 6:</strong> Example of an extracted facade texture
</p>


<div style="border-left:5px solid #4a90e2; padding:10px;">
    <strong>Suggestion:</strong> Introduce a vertical correction factor when estimating the height.
</div>

### 2.4. Height estimation methods

#### Connected components method

#### Depth map model method

#### U-Net model method

### 2.5. Output data

## 3. Assessment of results


## 4. Running the code

Running the example.

The code works according to the following structure:

```text
3DBAG_UNDERPASS_HEIGHTS/
├── data/
│   ├── 3dbag_tiles/
│   ├── oblique_images/
│   └── underpass_polygons/
├── src/
│   ├── data_preprocessing.py
│   ├── perspective_projection.py
│   ├── facade_extraction.py
│   ├── connected_components.py
│   ├── Depth-Anything-V2/
│   ├── depth_map.py
│   ├── u-net_model/
│   ├── u-net_model.py
│   └── main.py
└── output/
```

To install all dependencies run 
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
