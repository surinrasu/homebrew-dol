# homebrew-dol

本 Homebrew Tap 提供两项适用于 macOS 及 Linux 的 Formula，供使用者通过本机 HTTP 服务执行 [Degrees of Lewdity](https://gitgud.io/Vrelnir/degrees-of-lewdity) 的[中文本地化版本](https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization)。

两项 Formula 分别提供标准中文本地化版本，以及附有 Mod 载入器的版本。

> [!WARNING]
> 游戏含有成人内容，只供年满 18 岁的人士使用。使用前，请参阅官方发布页所载的免责声明、非商业使用规定及相关授权条款，并确保遵守有关规定。

## 使用方法

安装标准中文本地化版本：

```sh
brew install surinrasu/dol/dol-chs

```

如需使用 Mod 载入器，则安装：

```sh
brew install surinrasu/dol/dol-chs-mod

```

> [!NOTE]
> Mod 可执行 JavaScript。使用者只应载入来源可信的 Mod 档案。

部分版本的 Homebrew 或会要求使用者事先信任有关 Formula：

```sh
brew trust --formula surinrasu/dol/dol-chs
# 或
brew trust --formula surinrasu/dol/dol-chs-mod

```

两项 Formula 均独立运作，可同时安装。

### `dol-chs`

`dol-chs` 会按下列次序载入目前版本的官方资源：

1. 官方中文本地化套件 `ModI18N`
2. 官方图片套件 `GameOriginalImagePack`

直接执行 `dol-chs` 时，服务预设于 `http://127.0.0.1:8000/` 提供，并会自动开启浏览器。

使用者亦可指定常用的 HTTP 服务参数，例如：

```sh
dol-chs 8080 --bind 127.0.0.1 --no-open
dol-chs --directory /path/to/web-app --protocol HTTP/1.1

```

游戏存档储存于浏览器的本机储存空间，并与完整的 origin（即协议、主机名及端口号）绑定。如欲继续使用原有存档，须维持上述各项资料不变。

### `dol-chs-mod`

`dol-chs-mod` 预设不会载入任何 Mod，包括官方中文本地化套件及官方图片套件。使用者须透过参数明确指定需要载入的项目：

```sh
dol-chs-mod # 等价于 `dol-chs-mod --no-mods`
dol-chs-mod --i18n --images
dol-chs-mod --mod /path/to/mod.zip

```

`--no-mods` 不得与任何用于选择 Mod 的参数同时使用。

`--i18n`、`--images` 及可重复指定的 `--mod PATH`，会严格按照其在命令列出现的先后次序载入。因此，较后载入的 Mod 可覆盖较早载入的 Mod 中名称相同的内容。

例如，如欲以自订图片覆盖官方图片，可执行：

```sh
dol-chs-mod --i18n --images --mod /path/to/CustomImages.mod.zip

```

Mod 须为有效的 ZIP 压缩档案，并使用 Store 或 Deflate 压缩方式。压缩档案的根目录亦须载有有效的 `boot.json`。

完整参数列表可透过下列指令查阅：

```sh
dol-chs --help
dol-chs-mod --help

```

## Brew Services

透过 Brew Services 执行时，`dol-chs` 及 `dol-chs-mod` 预设分别使用 8000 及 8001 端口号：

```sh
brew services start dol-chs
brew services stop dol-chs

brew services start dol-chs-mod
brew services stop dol-chs-mod

```

在此运作方式下，`dol-chs-mod` 不会载入任何 Mod。

## 授权及权利

本项目按 [CC BY-NC-SA 4.0](./CC-LICENSE) 条款发布。

其中，由本项目独立完成且不属于上游项目的部分，另同时按 [MIT License](./MIT-LICENSE) 条款提供。游戏本体、中文本地化套件、图片套件及其它上游内容的权利仍分别属于其各自作者，并受各自适用的授权条款及使用条件规管。

[Vrelnir](https://vrelnir.blogspot.com/) 为 Degrees of Lewdity 原作的作者。本项目谨此感谢 Vrelnir、中文本地化团队及所有上游贡献者。
