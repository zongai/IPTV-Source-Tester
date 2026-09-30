DEFAULT_ALIASES = {
    "cctv-1": {"cctv1", "cctv-1", "cctv 1", "cctv1综合", "中央电视台1", "cctv-1 综合"},
}
def aliases_for(channel_id):
    return DEFAULT_ALIASES.get(channel_id, set())
