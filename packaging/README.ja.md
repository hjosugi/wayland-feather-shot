<!-- i18n: language-switcher -->
[English](README.md) | [日本語](README.ja.md)

# パッケージング

wayland-feather-shotの配布パッケージ。すべてのフォーマットはプロジェクトのコアな約束を守ります：**ネットワーク権限なし、テレメトリなし、ローカルのみ。**

## Flatpak

`flatpak/io.github.hjosugi.WaylandFeatherShot.yaml`はGNOMEランタイムに対してビルドされ（すでにGTK 4、PyGObject、pycairoを提供）、pipでパッケージを`--no-deps --no-build-isolation`でインストールします。これにより、ビルドはオフラインで再現可能です。マニフェストはWayland、IPC、DRI、`xdg-pictures`のみを許可します — **`--share=network`はなし**。スクリーンショット / スクリーンキャスト / グローバルショートカットは、Flatpakがデフォルトで公開するポータルにアクセスします。

```console
$ flatpak-builder --user --install --force-clean build-dir \
    packaging/flatpak/io.github.hjosugi.WaylandFeatherShot.yaml
$ flatpak run io.github.hjosugi.WaylandFeatherShot
```

## AUR

`aur/PKGBUILD`はホイールをビルドし、デスクトップエントリ、アイコン、AppStreamメタ情報、オートスタートファイルをインストールします。公開する前に`sha256sums=('SKIP')`をリリースタールボールの実際のチェックサムに置き換えてください。リリースアセットビルダーは、`wayland-feather-shot-$version-aur.tar.gz`でこれを自動的に行います。

```console
$ cd packaging/aur && makepkg -si
```

AURパッケージを公開または更新するには、最初にGitHubリリースタグを作成し、その後AUR gitリポジトリを同期します：

```console
$ scripts/publish-aur.sh vX.Y.Z
$ git -C dist/aur-vX.Y.Z push origin HEAD:master
```

`scripts/publish-aur.sh vX.Y.Z --push`を使用して、1つのコマンドでコミットとプッシュを行います。このスクリプトはGitHubタグのタールボールをダウンロードし、実際のチェックサムを書き込み、`.SRCINFO`を生成し、AURの更新をコミットします。AURアカウントにSSHアクセスが必要です。

現在のマシンにAUR SSHアクセスがない場合、ファイルを検査用にエクスポートします：

```console
$ scripts/publish-aur.sh vX.Y.Z --export-dir dist/aur-vX.Y.Z-files
```

リリースワークフローは、リポジトリのシークレット`AUR_SSH_PRIVATE_KEY`がメンテナのAURアカウントに登録された公開鍵を持つプライベートSSHキーに設定されている場合、AURに自動的に公開します。シークレットが存在しない場合、ワークフローはAURの公開をスキップし、GitHubリリースを作成します。

## AppImage

AppImageは意図的にホストランタイムラッパーです。アプリコード、デスクトップメタデータ、アイコンを含みますが、`/usr/bin/python3`で実行されるため、GTK4、PyGObject、pycairo、ポータル、GStreamer/PipeWireおよびその他のデスクトップ統合はREADMEに記載されたディストリビューションパッケージから提供されます。

既存のタグからすべてのリリースアセットをビルドします：

```console
$ python3 -m pip install --user build installer wheel setuptools
$ scripts/build-release-assets.sh vX.Y.Z
```

これにより、AppImage、Pythonホイール、Python sdist、修正されたAURソースバンドル、`SHA256SUMS`が`dist/release-vX.Y.Z/`に生成されます。

## AppStreamメタ情報

`../data/io.github.hjosugi.WaylandFeatherShot.metainfo.xml`はすべてのパッケージングフォーマットで共有され、ソフトウェアセンターに表示されます。次のコマンドで検証します：

```console
$ appstreamcli validate data/io.github.hjosugi.WaylandFeatherShot.metainfo.xml
```

## deb / rpm

まだ提供されていません。pip/`pyproject.toml`インストールと`install.sh`スクリプトがその間のソースインストールをカバーします。