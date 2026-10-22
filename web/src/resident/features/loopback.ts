/**
 * Demo video provider: the camera is sent through two WebRTC peer connections that live in this
 * page and talk to each other, so the "other party" is the device itself. Nothing leaves the
 * device, and no picture touches the server (invariant 14). A real provider would replace the
 * second peer with the remote party; the rest of the call screen stays the same.
 */
export interface Loopback {
  remote: MediaStream
  close: () => void
}

export async function startLoopback(local: MediaStream): Promise<Loopback> {
  const caller = new RTCPeerConnection()
  const callee = new RTCPeerConnection()
  const remote = new MediaStream()
  caller.onicecandidate = (e) => e.candidate && void callee.addIceCandidate(e.candidate)
  callee.onicecandidate = (e) => e.candidate && void caller.addIceCandidate(e.candidate)
  callee.ontrack = (e) => e.streams[0]?.getTracks().forEach((t) => remote.addTrack(t))
  local.getTracks().forEach((t) => caller.addTrack(t, local))
  const offer = await caller.createOffer()
  await caller.setLocalDescription(offer)
  await callee.setRemoteDescription(offer)
  const answer = await callee.createAnswer()
  await callee.setLocalDescription(answer)
  await caller.setRemoteDescription(answer)
  return {
    remote,
    close: () => {
      caller.close()
      callee.close()
      remote.getTracks().forEach((t) => t.stop())
    },
  }
}
