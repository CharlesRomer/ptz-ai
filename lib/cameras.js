// Camera registry — IPs configurable via .env
const CAMERAS = [
  { id: 1, ip: process.env.CAM1_IP || '192.168.100.86', name: 'Camera 1' },
  { id: 2, ip: process.env.CAM2_IP || '192.168.100.87', name: 'Camera 2' },
  { id: 3, ip: process.env.CAM3_IP || '192.168.100.88', name: 'Camera 3' },
];

let activeCameraId = 2; // .87 is the confirmed working camera

export const getCameras  = () => CAMERAS;
export const getCamera   = (id) => CAMERAS.find(c => c.id === id);
export const getActive   = () => CAMERAS.find(c => c.id === activeCameraId);
export const getActiveId = () => activeCameraId;

export function setActive(id) {
  if (!CAMERAS.find(c => c.id === id)) return false;
  activeCameraId = id;
  return true;
}
