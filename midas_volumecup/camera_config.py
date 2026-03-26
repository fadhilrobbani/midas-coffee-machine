class CameraConfig:
    def __init__(self, width: int, height: int):
        self.W = width
        self.H = height
        
        # Pure percentage-based dynamic resolution
        # Bright zone is the top 8% to 33% of the image
        self.BRIGHT_ROW_START = int(0.08 * self.H)
        self.BRIGHT_ROW_END   = int(0.33 * self.H)
        
        # Start searching for the shadow transition underneath the bright zone
        self.SEARCH_ROW_START = int(0.33 * self.H)
        
        # For dual cup split (not strictly used if single cup)
        self.SPLIT_COL = int(0.50 * self.W)
