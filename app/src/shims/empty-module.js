// Empty module shim -- used by Metro config to replace native-only packages
// (like LiveKit) when running in Expo Go.
module.exports = {};
module.exports.registerGlobals = function() {};
module.exports.AudioSession = {
  configureAudio: async function() {},
  startAudioSession: async function() {},
  stopAudioSession: async function() {},
};
module.exports.Room = function() {};
module.exports.RoomEvent = {};
module.exports.Track = { Kind: {} };
module.exports.ConnectionState = {};
