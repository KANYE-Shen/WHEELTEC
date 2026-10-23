#pragma once
#include <gz/gui/Plugin.hh>

// Finish GPU work at both sides of the Ogre -> Qt shared-texture boundary.
// CPU mutexes in MinimalScene do not wait for commands queued on the GPU.
class WheeltecRenderSync final : public gz::gui::Plugin
{
  Q_OBJECT
  public: void LoadConfig(const tinyxml2::XMLElement *) override;
  protected: bool eventFilter(QObject *, QEvent *) override;
  private: bool reported{false};
};
