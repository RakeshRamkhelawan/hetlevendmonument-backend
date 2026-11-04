<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>404</title>
    <style>
      :root {
        --Bg-Primary: #fff;
        --Labels-Primary: rgba(0, 0, 0, 0.9);
        --Labels-Tertiary: rgba(0, 0, 0, 0.45);
      }

      @media (prefers-color-scheme: dark) {
        :root {
          --Bg-Primary: #fff;
          --Labels-Primary: rgba(0, 0, 0, 0.9);
          --Labels-Tertiary: rgba(0, 0, 0, 0.45);
        }
      }

      * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
      }

      body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
          "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue",
          Helvetica, Arial, sans-serif;
        line-height: 1.5;
        /*min-height: 100vh;*/
        height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-direction: column;
        position: relative;
        overflow-x: hidden;
        background: var(--Bg-Primary);
      }

      /* Background decoration */
      body::before {
        content: "";
        position: absolute;
        top: -50%;
        left: -50%;
        background: radial-gradient(
            circle at 30% 70%,
            var(--others-km-blue-10) 0%,
            transparent 50%
          ),
          radial-gradient(
            circle at 80% 20%,
            var(--fills-f1) 0%,
            transparent 50%
          );
        z-index: -1;
      }
      .back-button {
        color: var(--Bg-Primary);
        text-align: center;
        font-size: 14px;
        font-weight: 500;
        line-height: 20px;
        display: flex;
        height: 40px;
        padding: 0 12px;
        justify-content: center;
        align-items: center;
        border-radius: 12px;
        background: var(--Labels-Primary);
        cursor: pointer;
        border: none;
      }
      a {
        color: var(--Bg-Primary);
        text-decoration: none;
      }
      .text {
        color: var(--Labels-Tertiary);
        text-align: center;
        font-size: 16px;
        font-weight: 400;
        line-height: 24px;
        margin-bottom: 32px;
      }
      .warn-img {
        width: 56px;
        height: 56px;
        margin-bottom: 8px;
      }
      .logo-img {
        width: 85px;
        height: 30px;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-left: 24px;
      }
      .top-header {
        text-align: left;
        width: 100%;
        height: 58px;
        display: flex;
        align-items: center;
        position: fixed;
        top: 0;
        border-bottom: 0.5px solid rgba(0, 0, 0, 0.13);
      }
    </style>
  </head>

  <body>
    <div class="top-header">
      <img
        class="logo-img"
        src="data:image/png;base64,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"
      />
    </div>
    <svg
      class="warn-img"
      width="56"
      height="56"
      viewBox="0 0 56 56"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M25.6667 4.6665H30.3334V6.99984H25.6667V4.6665Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M23.3334 6.99984H25.6667V9.33317H23.3334V6.99984Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M21 9.33317H23.3334V13.9998H21V9.33317Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M18.6667 13.9998H21V18.6665H18.6667V13.9998Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M26.8334 16.3332H29.1667V32.6665H26.8334V16.3332Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M26.8334 37.3332H29.1667V41.9998H26.8334V37.3332Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M26.8334 38.4998V40.8332H25.6667V38.4998H26.8334Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M30.3334 38.4998V40.8332H29.1667V38.4998H30.3334Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M16.3334 18.6665H18.6667V23.3332H16.3334V18.6665Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M14 23.3332H16.3334V27.9998H14V23.3332Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M11.6667 27.9998H14V32.6665H11.6667V27.9998Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M42 27.9998H44.3334V32.6665H42V27.9998Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M44.3334 32.6665H46.6667V37.3332H44.3334V32.6665Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M9.33335 32.6665H11.6667V37.3332H9.33335V32.6665Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M7.00002 37.3332H9.33335V41.9998H7.00002V37.3332Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M4.66669 41.9998H7.00002V44.3332H4.66669V41.9998Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M7.00002 44.3332H9.33335V46.6665H7.00002V44.3332Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M46.6667 44.3332H49V46.6665H46.6667V44.3332Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M49 41.9998H51.3334V44.3332H49V41.9998Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M9.33335 46.6665H46.6667V48.9998H9.33335V46.6665Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M46.6667 37.3332H49V41.9998H46.6667V37.3332Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M32.6667 9.33317H35V13.9998H32.6667V9.33317Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M35 13.9998H37.3334V18.6665H35V13.9998Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M37.3334 18.6665H39.6667V23.3332H37.3334V18.6665Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M39.6667 23.3332H42V27.9998H39.6667V23.3332Z"
        fill="black"
        fill-opacity="0.45"
      />
      <path
        d="M30.3334 6.99984H32.6667V9.33317H30.3334V6.99984Z"
        fill="black"
        fill-opacity="0.45"
      />
    </svg>
    <div class="text">404 Page Not Found</div>
    <a rel="noreferrer noopener nofollow" href="https://www.kimi.com/">
      <button class="back-button">Back to Kimi</button>
    </a>
  </body>
</html>
