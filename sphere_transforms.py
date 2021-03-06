#### Python code for performing Mobius transformations to equirectangular images, by Henry Segerman, Jan 2016

#### This code is provided as is, with no warranty or expectation of correctness. Do not use for mission critical
#### purposes without thoroughly checking it yourself. 

#### This code uses the Python Imaging Library (PIL), currently supported as "Pillow", available from https://python-pillow.github.io

#### For more details, see the blogpost at http://elevr.com/spherical-video-editing-effects-with-mobius-transformations/
#### and the tech demo spherical video at https://www.youtube.com/watch?v=oVwmF_vrZh0

import os
from math import *
from vectors_and_matrices import vector, dot, cross, matrix2_inv, matrix_mult, matrix_mult_vector
from PIL import Image
import cmath
from datetime import datetime
import uuid
import sys

def angles_from_pixel_coords(point, x_size = 1000):
  """map from pixel coords to (0, 2*pi) x (-pi/2, pi/2) rectangle"""
  y_size = x_size/2  #assume equirectangular format
  return ((point[0] + 0.5)* 2*pi/float(x_size), point[1] * pi/float(y_size-1) - 0.5*pi)

def pixel_coords_from_angles(point, x_size = 1000):
  """map from (0, 2*pi) x (-pi/2, pi/2) rectangle to pixel coords"""
  y_size = x_size/2  #assume equirectangular format
  return (point[0] * float(x_size)/(2*pi) - 0.5, (point[1] + 0.5*pi)* float(y_size-1)/pi)

def angles_from_sphere(point):
  """map from sphere in R^3 to (0, 2*pi) x (-pi/2, pi/2) rectangle (i.e. perform equirectangular projection)"""
  x,y,z = point
  longitude = atan2(y,x)
  if longitude < 0.0:
    longitude = longitude + 2*pi
  r = sqrt(x*x+y*y)
  latitude = atan2(z,r)
  return (longitude, latitude)

def sphere_from_angles(point): 
  """map from (0, 2*pi) x (-pi/2, pi/2) rectangle to sphere in R^3 (i.e. perform inverse of equirectangular projection)"""
  x,y = point
  horiz_radius = cos(y)
  return vector([horiz_radius*cos(x), horiz_radius*sin(x), sin(y)])
  
def sphere_from_pixel_coords(point, x_size = 1000):
  """map from pixel coords to sphere in R^3"""
  return sphere_from_angles(angles_from_pixel_coords(point, x_size = x_size))

def CP1_from_sphere(point):
  """map from sphere in R^3 to CP^1"""
  x,y,z = point
  if z < 0:
    return (complex(x,y), complex(1-z))
  else:
    return (complex(1+z), complex(x,-y))

def sphere_from_CP1(point):
  """map from CP^1 to sphere in R^3"""
  z1,z2 = point
  if abs(z2) > abs(z1):
    z = z1/z2
    x,y = z.real, z.imag
    denom = 1 + x*x + y*y
    return [2*x/denom, 2*y/denom, (denom - 2.0)/denom]
  else:
    z = (z2/z1).conjugate()
    x,y = z.real, z.imag
    denom = 1 + x*x + y*y
    return [2*x/denom, 2*y/denom, (2.0 - denom)/denom]

def clamp(pt, x_size):
  """clamp to size of input, including wrapping around in the x direction""" 
  y_size = x_size/2       # assume equirectangular format
  pt[0] = pt[0] % x_size  # wrap around in the x direction
  if pt[1] < 0:
    pt[1] = 0
  elif pt[1] > y_size - 1:
    pt[1] = y_size - 1
  return pt

def get_pixel_colour(pt, s_im, x_size = 1000):
  """given pt in integers, get pixel colour on the source image as a vector in the colour cube"""
  pt = clamp(pt, x_size)
  return vector(s_im[pt[0], pt[1]])

def get_interpolated_pixel_colour(pt, s_im, x_size = 1000):
  """given pt in floats, linear interpolate pixel values nearby to get a good colour"""
  ### for proper production software, more than just the four pixels nearest to the input point coordinates should be used in many cases
  x,y = int(floor(pt[0])), int(floor(pt[1]))  #integer part of input coordinates
  f,g = pt[0]-x, pt[1]-y                      #fractional part of input coordinates
  out_colour = (1-f)*( (1-g)*get_pixel_colour([x,y], s_im, x_size = x_size) + g*get_pixel_colour([x,y+1], s_im, x_size = x_size) ) \
          +  f*( (1-g)*get_pixel_colour([x+1,y], s_im, x_size = x_size) + g*get_pixel_colour([x+1,y+1], s_im, x_size = x_size) )
  out_colour = [int(round(coord)) for coord in out_colour]
  return tuple(out_colour)

######## Functions generating SL(2,C) matrices 

# Note that we only care about the matrices projectively. I.e. [[a,b],[c,d]] acts in exactly the same way on points of CP^1 as
# [[-a,-b],[-c,-d]], so we can also think of these matrices as being in PSL(2,C).

def inf_zero_one_to_triple(p,q,r):
  """returns SL(2,C) matrix that sends the three points infinity, zero, one to given input points p,q,r"""
  ### infinity = [1,0], zero = [0,1], one = [1,1] in CP^1
  p1,p2=p
  q1,q2=q
  r1,r2=r
  M = [[p1,q1],[p2,q2]]
  Minv = matrix2_inv(M)
  [mu,lam] = matrix_mult_vector(matrix2_inv([[p1,q1],[p2,q2]]), [r1,r2])
  return [[mu*p1, lam*q1],[mu*p2, lam*q2]]

def two_triples_to_SL(a1,b1,c1,a2,b2,c2):
  """returns SL(2,C) matrix that sends the three CP^1 points a1,b1,c1 to a2,b2,c2"""
  return matrix_mult( inf_zero_one_to_triple(a2,b2,c2), matrix2_inv(inf_zero_one_to_triple(a1,b1,c1) ) ) 

def three_points_to_three_points_pixel_coords(p1, q1, r1, p2, q2, r2, x_size = 1000):
  """returns SL(2,C) matrix that sends the three pixel coordinate points a1,b1,c1 to a2,b2,c2"""
  p1,q1,r1,p2,q2,r2 = [CP1_from_sphere(sphere_from_pixel_coords(point, x_size = x_size)) for point in [p1,q1,r1,p2,q2,r2]]
  return two_triples_to_SL(p1,q1,r1,p2,q2,r2)

def get_vector_perp_to_p_and_q(p, q):
  """p and q are distinct points on sphere, return a unit vector perpendicular to both"""
  if abs(dot(p,q) + 1) < 0.0001: ### deal with the awkward special case when p and q are antipodal on the sphere
      if abs(dot(p, vector([1,0,0]))) > 0.9999: #p is parallel to (1,0,0)
        return vector([0,1,0])
      else:
        return cross(p, vector([1,0,0])).normalised() 
  else:
    return cross(p, q).normalised()

def rotate_sphere_points_p_to_q(p, q):
  """p and q are points on the sphere, return SL(2,C) matrix rotating image of p to image of q on CP^1"""
  p, q = vector(p), vector(q)
  CP1p, CP1q = CP1_from_sphere(p), CP1_from_sphere(q)
  if abs(dot(p,q) - 1) < 0.0001:
    return [[1,0],[0,1]]
  else:
    r = get_vector_perp_to_p_and_q(p, q)
    CP1r, CP1mr = CP1_from_sphere(r), CP1_from_sphere(-r)
    return two_triples_to_SL(CP1p, CP1r, CP1mr, CP1q, CP1r, CP1mr) 

def rotate_pixel_coords_p_to_q(p, q, x_size = 1000):
  """p and q are pixel coordinate points, return SL(2,C) matrix rotating image of p to image of q on CP^1"""
  p = sphere_from_pixel_coords(p, x_size = x_size)
  q = sphere_from_pixel_coords(q, x_size = x_size)
  return rotate_sphere_points_p_to_q(p,q)

def zoom_in_on_pixel_coords(p, zoom_factor, x_size = 1000):
  """p is pixel coordinate point, return SL(2,C) matrix zooming in on p by a factor of scale"""
  # Note that the zoom factor is only accurate at the point p itself. As we move away from p, we zoom less and less.
  # We zoom with the inverse zoom_factor towards/away from the antipodal point to p.
  M_rot = rotate_pixel_coords_p_to_q( p, (0,0), x_size = x_size)
  M_scl = [[zoom_factor,0],[0,1]] ### zoom in on zero in CP^1
  return matrix_mult( matrix_mult(matrix2_inv(M_rot), M_scl), M_rot )

##### Apply functions to images

def apply_SL2C_elt_to_image(M, source_image_filename, out_x_size = None, save_filename = "sphere_transforms_test.png"):
  """apply an element of SL(2,C) (i.e. a matrix) to an equirectangular image file"""
  Minv = matrix2_inv(M)  # to push an image forwards by M, we pull the pixel coordinates of the output backwards 
  source_image = Image.open(source_image_filename)
  s_im = source_image.load()  # faster pixel by pixel access 
  in_x_size, in_y_size = source_image.size
  if out_x_size == None:
    out_x_size, out_y_size = source_image.size
  else:
    out_y_size = out_x_size/2
  out_image = Image.new("RGB", (out_x_size, out_y_size))
  o_im = out_image.load()  # faster pixel by pixel access 

  for i in range(out_x_size): 
    for j in range(out_y_size):
      pt = (i,j)
      pt = angles_from_pixel_coords(pt, x_size = out_x_size)
      pt = sphere_from_angles(pt)
      pt = CP1_from_sphere(pt)
      pt = matrix_mult_vector(Minv, pt)
      pt = sphere_from_CP1(pt)
      pt = angles_from_sphere(pt)
      pt = pixel_coords_from_angles(pt, x_size = in_x_size)
      o_im[i,j] = get_interpolated_pixel_colour(pt, s_im, x_size = in_x_size)
  out_image.save(save_filename)
  
def rotate_equirect_image(image_filename, from_x, to_x):
  s_img = Image.open(image_filename)
  dist = abs(from_x - to_x)
  
  l_box = (0,0,0,0)
  r_box = (0,0,0,0)
  
  if(from_x < to_x):
    l_box = (0, 0, s_img.size[0] - dist, s_img.size[1])
    r_box = (s_img.size[0] - dist,0,s_img.size[0],s_img.size[1])
  else:
    l_box = (0, 0, dist, s_img.size[1])
    r_box = (dist, 0, s_img.size[0], s_img.size[1])
  
  right = s_img.crop(r_box)
  left = s_img.crop(l_box)
  
  new_im = Image.new('RGB', s_img.size)
  new_im.paste(right,(0,0))
  new_im.paste(left,(right.size[0],0))
  
  temp_file_name = str(uuid.uuid4()) + ".png"
  new_im.save(temp_file_name,"PNG")
  return temp_file_name

def generate_image(zoom_center_pixel_coords, zoom_factor, zoom_cutoff, source_image_filename_A, source_image_filename_B, out_x_size = None, zoom_loop_value = 0.0, save_filename = "sphere_transforms_test.png"):
  """produces a zooming effect image from one equirectangular image into another equirectangular image"""
  source_image_A = Image.open(source_image_filename_A)
  s_im_A = source_image_A.load()
  source_image_B = Image.open(source_image_filename_B)
  s_im_B = source_image_B.load()
  
  in_x_size, in_y_size = source_image_A.size
  
  M_rot = rotate_pixel_coords_p_to_q(zoom_center_pixel_coords, (0,0), x_size = in_x_size)
  M_rot_inv = matrix2_inv(M_rot)
  out_y_size = out_x_size/2
  out_image = Image.new("RGB", (out_x_size, out_y_size))
  o_im = out_image.load()

  for i in range(out_x_size): 
    for j in range(out_y_size):
      pt = (i,j)
      pt = angles_from_pixel_coords(pt, x_size = out_x_size)
      pt = sphere_from_angles(pt)
      pt = CP1_from_sphere(pt)
      pt = matrix_mult_vector(M_rot, pt)

      # if ever you don't know how to do some operation in complex projective coordinates, it's almost certainly 
      # safe to just switch back to ordinary complex numbers by pt = pt[0]/pt[1]. The only danger is if pt[1] == 0, 
      # or is near enough to cause floating point errors. In this application, you are probably fine unless you 
      # make some very specific choices of where to zoom to etc. 
      pt = pt[0]/pt[1]
      pt = cmath.log(pt)

      # zoom_loop_value is between 0 and 1, vary this from 0.0 to 1.0 to animate frames zooming into the transition animation image
      pt = complex(pt.real + log(zoom_factor) * zoom_loop_value, pt.imag) 
      
      recurse_value = (pt.real + zoom_cutoff) / log(zoom_factor)
      
      # zoom_cutoff alters the slice of the input image that we use, so that it covers mostly the original image, together with 
      # some of the zoomed image that was composited with the original. The slice needs to cover the seam between the two
      # (i.e. the picture frame you are using, but should cover as little as possible of the zoomed version of the image.
      
      if(floor(recurse_value) >= 0.0):
        # main and prev spheres => do nothing to pt
        someval = "do nothing further"
      elif(floor(recurse_value) == -1.0):
        # this is the "next sphere"
        pt = complex((pt.real + zoom_cutoff) % log(zoom_factor) - zoom_cutoff, pt.imag)
      elif(floor(recurse_value) == -2.0):
        pt = complex((pt.real + zoom_cutoff) % log(zoom_factor) - zoom_cutoff - log(zoom_factor), pt.imag)
      elif(floor(recurse_value) == -3.0):
        pt = complex((pt.real + zoom_cutoff) % log(zoom_factor) - zoom_cutoff - (log(zoom_factor) * 2), pt.imag)
      else:
        # this is "future spheres"
        pt = complex((pt.real + zoom_cutoff) % log(zoom_factor) - zoom_cutoff - (log(zoom_factor) * 3.0), pt.imag)
      
      pt = cmath.exp(pt)
      pt = [pt, 1] #back to projective coordinates
      pt = matrix_mult_vector(M_rot_inv, pt)
      pt = sphere_from_CP1(pt)
      pt = angles_from_sphere(pt)
      pt = pixel_coords_from_angles(pt, x_size = in_x_size)
      
      if(floor(recurse_value) >= 0):
        o_im[i,j] = get_interpolated_pixel_colour(pt, s_im_A, in_x_size)
      else:
        o_im[i,j] = get_interpolated_pixel_colour(pt, s_im_B, in_x_size)

  sys.stdout.write(" . " + datetime.now().strftime('%H:%M:%S'))
  # print datetime.now().strftime('%H:%M:%S') + ": finished " + save_filename
  out_image.save(save_filename)


######## Test 

if __name__ == "__main__":
  #M = zoom_in_on_pixel_coords((360,179.5), 2, x_size = 720) 
  #apply_SL2C_elt_to_image( M, 'equirectangular_test_image.png', save_filename = 'scaled_test_image.png' )

  rotate_equirect_image('./buddha/37e2e38392994f83b67c96a6c9e71e1f_pano.jpg', 4000, 100)


