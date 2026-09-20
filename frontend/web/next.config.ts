import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /*
   * Next's dev-tools badge defaults to bottom-left, which is exactly where
   * this product's sidebar footer sits - it covered the org name and the
   * connection state, and read as a broken avatar in screenshots. It is a
   * dev-only overlay and never ships, but moving it keeps development
   * looking like production. Compile and runtime errors still surface.
   */
  devIndicators: {
    position: "bottom-right",
  },
};

export default nextConfig;
