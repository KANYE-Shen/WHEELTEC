#include "RenderSync.hh"
#include <QOpenGLContext>
#include <QOpenGLFunctions>
#include <QQuickWindow>
#include <gz/common/Console.hh>
#include <gz/gui/Application.hh>
#include <gz/gui/GuiEvents.hh>
#include <gz/gui/MainWindow.hh>
#include <gz/plugin/Register.hh>

namespace
{
void FinishCurrentContext()
{
  if (auto *context = QOpenGLContext::currentContext())
    context->functions()->glFinish();
}
}

void WheeltecRenderSync::LoadConfig(const tinyxml2::XMLElement *)
{
  auto *window = gz::gui::App()->findChild<gz::gui::MainWindow *>();
  if (!window)
    return;
  window->installEventFilter(this);
  // Qt must finish sampling the shared texture before Ogre can overwrite it.
  QObject::connect(window->QuickWindow(), &QQuickWindow::afterRendering,
                   this, &FinishCurrentContext, Qt::DirectConnection);
}

bool WheeltecRenderSync::eventFilter(QObject *, QEvent *event)
{
  if (event->type() == gz::gui::events::Render::kType)
  {
    // Render is sent on the Ogre worker before its CPU lock releases Qt.
    // Wait for all pixels, rather than only CPU command submission, to finish.
    FinishCurrentContext();
    if (!this->reported)
    {
      ignmsg << "WHEELTEC GUI GPU synchronization active" << std::endl;
      this->reported = true;
    }
  }
  return false;
}

IGNITION_ADD_PLUGIN(WheeltecRenderSync, gz::gui::Plugin)
