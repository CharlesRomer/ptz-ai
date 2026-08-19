// HTTP-CGI command wrappers for PTZOptics cameras
export async function cgiGET(ip, path) {
  const url = `http://${ip}${path}`;
  const res = await fetch(url, { signal: AbortSignal.timeout(4000) });
  return { url, status: res.status, ok: res.ok };
}

const ptz   = (ip, cmd) => cgiGET(ip, `/cgi-bin/ptzctrl.cgi?${cmd}`);
const param = (ip, cmd) => cgiGET(ip, `/cgi-bin/param.cgi?${cmd}`);

export const cgi = {
  // Movement
  pan_tilt:      (ip, dir, ps, ts) => ptz(ip, `ptzcmd&${dir}&${ps}&${ts}`),
  stop:          (ip)              => ptz(ip, 'ptzcmd&ptzstop'),
  zoom:          (ip, action, s)   => ptz(ip, `ptzcmd&${action}&${s}`),
  zoom_stop:     (ip)              => ptz(ip, 'ptzcmd&zoomstop'),
  focus:         (ip, action, s)   => ptz(ip, `ptzcmd&${action}&${s}`),
  focus_stop:    (ip)              => ptz(ip, 'ptzcmd&focusstop'),
  focus_mode:    (ip, mode)        => param(ip, `ptzcmd&${mode === 'auto' ? 'unlock' : 'lock'}_mfocus`),
  home:          (ip)              => ptz(ip, 'ptzcmd&home'),
  preset_recall: (ip, n)           => ptz(ip, `ptzcmd&poscall&${n}`),
  preset_save:   (ip, n)           => ptz(ip, `ptzcmd&posset&${n}`),

  // Image controls (always via CGI, VISCA doesn't cover these)
  autotrack:  (ip, on)   => ptz(ip, `post_image_value&autotrack&${on ? 2 : 3}`),
  wb_mode:    (ip, mode) => param(ip, `post_image_value&wbmode&${mode}`),
  ae_mode:    (ip, mode) => param(ip, `post_image_value&aemode&${mode}`),
  iris:       (ip, val)  => param(ip, `post_image_value&iris&${val}`),
  shutter:    (ip, val)  => param(ip, `post_image_value&shutter&${val}`),
  gain:       (ip, val)  => param(ip, `post_image_value&gain&${val}`),
  rgain:      (ip, val)  => param(ip, `post_image_value&rgain&${val}`),
  bgain:      (ip, val)  => param(ip, `post_image_value&bgain&${val}`),
  sharpness:  (ip, val)  => param(ip, `post_image_value&sharpness&${val}`),
};
