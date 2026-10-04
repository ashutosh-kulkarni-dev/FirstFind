import { useEffect, useRef } from 'react'
import * as THREE from 'three'

/**
 * Three.js hero background: a slowly-drifting field of glowing particles
 * plus a wireframe torus-knot "thread ball" — a nod to fabric/threads.
 * Kept deliberately light (one knot + ~1200 points, no postprocessing)
 * so it runs at 60fps on integrated graphics.
 */
export default function Hero3D() {
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(60, el.clientWidth / el.clientHeight, 0.1, 100)
    camera.position.set(0, 0, 9)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(el.clientWidth, el.clientHeight)
    el.appendChild(renderer.domElement)

    // --- wireframe torus knot (thread ball) ---
    const knot = new THREE.Mesh(
      new THREE.TorusKnotGeometry(2.3, 0.62, 140, 18, 2, 3),
      new THREE.MeshBasicMaterial({ color: 0xc8f048, wireframe: true, transparent: true, opacity: 0.16 }),
    )
    knot.position.set(3.4, 0.2, -2)
    scene.add(knot)

    // --- particle field ---
    const N = 1200
    const positions = new Float32Array(N * 3)
    for (let i = 0; i < N; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 26
      positions[i * 3 + 1] = (Math.random() - 0.5) * 16
      positions[i * 3 + 2] = (Math.random() - 0.5) * 12 - 2
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    const dots = new THREE.Points(geo, new THREE.PointsMaterial({
      color: 0xf4a988, size: 0.035, transparent: true, opacity: 0.75,
    }))
    scene.add(dots)

    const dots2 = new THREE.Points(geo.clone(), new THREE.PointsMaterial({
      color: 0xc8f048, size: 0.05, transparent: true, opacity: 0.5,
    }))
    dots2.rotation.z = 1.3
    scene.add(dots2)

    // --- mouse parallax ---
    let mx = 0, my = 0
    const onMouse = (e) => {
      mx = (e.clientX / window.innerWidth - 0.5) * 2
      my = (e.clientY / window.innerHeight - 0.5) * 2
    }
    window.addEventListener('mousemove', onMouse)

    const onResize = () => {
      camera.aspect = el.clientWidth / el.clientHeight
      camera.updateProjectionMatrix()
      renderer.setSize(el.clientWidth, el.clientHeight)
    }
    window.addEventListener('resize', onResize)

    const clock = new THREE.Clock()
    let raf
    const animate = () => {
      raf = requestAnimationFrame(animate)
      const t = clock.getElapsedTime()
      knot.rotation.x = t * 0.12
      knot.rotation.y = t * 0.18
      dots.rotation.y = t * 0.015
      dots2.rotation.y = -t * 0.01
      camera.position.x += (mx * 0.6 - camera.position.x) * 0.03
      camera.position.y += (-my * 0.4 - camera.position.y) * 0.03
      camera.lookAt(0, 0, 0)
      renderer.render(scene, camera)
    }
    animate()

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('mousemove', onMouse)
      window.removeEventListener('resize', onResize)
      renderer.dispose()
      geo.dispose()
      el.removeChild(renderer.domElement)
    }
  }, [])

  return <div ref={ref} className="hero-canvas" />
}
